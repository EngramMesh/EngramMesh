#!/usr/bin/env ruby
# frozen_string_literal: true

require "open3"
require "optparse"
require "yaml"

options = {}
parser = OptionParser.new do |arguments|
  arguments.banner = "usage: #{File.basename($PROGRAM_NAME)} --root ROOT --actionlint PATH"
  arguments.on("--root ROOT") { |root| options[:root] = root }
  arguments.on("--actionlint PATH") { |path| options[:actionlint] = path }
end

begin
  parser.parse!
rescue OptionParser::ParseError => error
  warn error.message
  warn parser.banner
  exit 2
end

unless ARGV.empty? && options.values_at(:root, :actionlint).all?
  warn parser.banner
  exit 2
end

root = File.expand_path(options.fetch(:root))
actionlint = File.expand_path(options.fetch(:actionlint))

begin
  actionlint_stdout, actionlint_stderr, actionlint_status =
    Open3.capture3(actionlint, chdir: root)
rescue SystemCallError => error
  warn "actionlint failed to start: #{error.message}"
  exit 1
end

$stdout.print(actionlint_stdout)
$stderr.print(actionlint_stderr)
exit 1 unless actionlint_status.success?

workflow_paths = Dir.glob(File.join(root, ".github/workflows/*.{yml,yaml}")).sort
workflows = workflow_paths.map do |path|
  begin
    document = YAML.safe_load(
      File.read(path),
      permitted_classes: [],
      permitted_symbols: [],
      aliases: false
    )
  rescue Errno::EACCES, Errno::ENOENT => error
    warn "#{path.delete_prefix("#{root}/")}: cannot read file: #{error.message}"
    exit 1
  rescue Psych::Exception => error
    warn "#{path.delete_prefix("#{root}/")}: invalid YAML: #{error.message}"
    exit 1
  end
  [path.delete_prefix("#{root}/"), document]
end

expected_workflows = {
  "Repository policy" => "repository-policy",
  "External links" => "external-links"
}
expected_workflows.each_key do |workflow_name|
  matching_paths = workflows.each_with_object([]) do |(relative_path, document), paths|
    paths << relative_path if document["name"] == workflow_name
  end
  next unless matching_paths.length > 1

  warn "duplicate workflow name: #{workflow_name}: #{matching_paths.join(', ')}"
  exit 1
end

workflows.each do |relative_path, document|
  next if document["permissions"] == { "contents" => "read" }

  warn "#{relative_path}: top-level permissions must be exactly contents: read"
  exit 1
end

def each_uses_value(node, &block)
  case node
  when Hash
    node.each do |key, value|
      block.call(value) if key == "uses" && value.is_a?(String)
      each_uses_value(value, &block)
    end
  when Array
    node.each { |value| each_uses_value(value, &block) }
  end
end

workflows.each do |relative_path, document|
  each_uses_value(document) do |value|
    next if value.match?(/\A[^@\s]+@[0-9a-f]{40}\z/)

    warn "#{relative_path}: unpinned uses: #{value}"
    exit 1
  end
end

workflows.each do |relative_path, document|
  jobs = document["jobs"]
  next unless jobs.is_a?(Hash)

  jobs.each do |job_name, job|
    next unless job.is_a?(Hash) && job.key?("permissions")

    warn "#{relative_path}: job #{job_name} must not define permissions"
    exit 1
  end
end

workflows_by_name = workflows.each_with_object({}) do |(relative_path, document), result|
  result[document["name"]] = [relative_path, document]
end

expected_workflows.each_key do |workflow_name|
  next if workflows_by_name.key?(workflow_name)

  warn "missing workflow name: #{workflow_name}"
  exit 1
end

expected_workflows.each do |workflow_name, job_name|
  relative_path, document = workflows_by_name.fetch(workflow_name)
  jobs = document["jobs"]
  next if jobs.is_a?(Hash) && jobs.key?(job_name)

  warn "#{relative_path}: missing job: #{job_name}"
  exit 1
end

required_path, required_workflow = workflows_by_name.fetch("Repository policy")
required_job = required_workflow.fetch("jobs").fetch("repository-policy")
required_run_lines =
  Array(required_job["steps"]).each_with_object([]) do |step, lines|
    next unless step.is_a?(Hash) && step["run"].is_a?(String)

    lines.concat(step["run"].lines.map(&:strip))
  end
[
  'git cat-file -e "${HEAD_SHA}^{commit}"',
  'git cat-file -e "${TREE_SHA}^{commit}"',
  'git cat-file -e "${BASE_SHA}^{commit}"'
].each do |guard|
  next if required_run_lines.include?(guard)

  warn "#{required_path}: missing required guard: #{guard}"
  exit 1
end

required_concurrency = required_workflow["concurrency"]
required_group =
  if required_concurrency.is_a?(Hash)
    required_concurrency["group"]
  else
    required_concurrency
  end
unless required_group.is_a?(String) && required_group.start_with?("required-policy-")
  warn "#{required_path}: concurrency group must start with required-policy-"
  exit 1
end

external_path, external_workflow = workflows_by_name.fetch("External links")
external_concurrency = external_workflow["concurrency"]
external_group =
  if external_concurrency.is_a?(Hash)
    external_concurrency["group"]
  else
    external_concurrency
  end
unless external_group.is_a?(String) && external_group.start_with?("external-links-")
  warn "#{external_path}: concurrency group must start with external-links-"
  exit 1
end

def workflow_events(workflow)
  return workflow["on"] if workflow.key?("on")

  workflow[true]
end

def workflow_event_mapping(workflow)
  events = workflow_events(workflow)
  events if events.is_a?(Hash)
end

def workflow_event_present?(workflow, event_name)
  events = workflow_event_mapping(workflow)
  events && events.key?(event_name)
end

def workflow_event_branches_include_main_without_negative_patterns?(workflow, event_name)
  events = workflow_event_mapping(workflow)
  event = events && events[event_name]
  return false unless event.is_a?(Hash)

  patterns =
    case event["branches"]
    when String
      [event["branches"]]
    when Array
      event["branches"]
    else
      return false
    end

  patterns.include?("main") &&
    patterns.all? { |pattern| pattern.is_a?(String) && !pattern.start_with?("!") }
end

def workflow_event?(workflow, event_name)
  events = workflow_events(workflow)
  case events
  when Hash
    events.key?(event_name)
  when Array
    events.include?(event_name)
  else
    events == event_name
  end
end

TOKEN_PROPERTIES = {
  "github" => "token",
  "secrets" => "github_token"
}.freeze

def actions_expression_bodies(value)
  source = value.b
  bodies = []
  search_from = 0
  while (opening = source.index("${{".b, search_from))
    body_start = opening + 3
    index = body_start
    in_string = false
    closed = false
    while index < source.bytesize - 1
      byte = source.getbyte(index)
      if in_string
        if byte == 39 && source.getbyte(index + 1) == 39
          index += 2
        elsif byte == 39
          in_string = false
          index += 1
        else
          index += 1
        end
      elsif byte == 39
        in_string = true
        index += 1
      elsif byte == 125 && source.getbyte(index + 1) == 125
        bodies << source.byteslice(body_start, index - body_start)
        search_from = index + 2
        closed = true
        break
      else
        index += 1
      end
    end
    break unless closed
  end
  bodies
end

def expression_space?(byte)
  [9, 10, 11, 12, 13, 32].include?(byte)
end

def identifier_start?(byte)
  byte &&
    ((byte >= 65 && byte <= 90) ||
     (byte >= 97 && byte <= 122) ||
     byte == 95)
end

def identifier_part?(byte)
  identifier_start?(byte) || (byte && byte >= 48 && byte <= 57)
end

def skip_expression_space(source, index)
  index += 1 while expression_space?(source.getbyte(index))
  index
end

def read_identifier(source, index)
  return [nil, index] unless identifier_start?(source.getbyte(index))

  finish = index + 1
  finish += 1 while identifier_part?(source.getbyte(finish))
  [source.byteslice(index, finish - index).downcase, finish]
end

def skip_single_quoted_string(source, index)
  index += 1
  while index < source.bytesize
    if source.getbyte(index) == 39 && source.getbyte(index + 1) == 39
      index += 2
    elsif source.getbyte(index) == 39
      return index + 1
    else
      index += 1
    end
  end
  index
end

def static_bracket_property(source, index)
  index = skip_expression_space(source, index)
  quote = source.getbyte(index)
  return [:dynamic, nil, index] unless [34, 39].include?(quote)

  property = +"".b
  index += 1
  closed = false
  while index < source.bytesize
    byte = source.getbyte(index)
    if quote == 39 && byte == 39 && source.getbyte(index + 1) == 39
      property << 39
      index += 2
    elsif byte == quote
      index += 1
      closed = true
      break
    else
      property << byte
      index += 1
    end
  end
  return [:dynamic, nil, index] unless closed

  index = skip_expression_space(source, index)
  return [:dynamic, nil, index] unless source.getbyte(index) == 93

  [:static, property.downcase, index + 1]
end

# This is intentionally a conservative lexical detector, not an Actions
# expression evaluator. Root github and secrets contexts, exact token
# properties, and non-static bracket access directly on github or secrets are
# rejected. Static non-token access such as github['sha'] remains allowed.
def token_access_in_expression?(expression)
  source = expression.b
  index = 0
  while index < source.bytesize
    if source.getbyte(index) == 39
      index = skip_single_quoted_string(source, index)
      next
    end

    identifier, finish = read_identifier(source, index)
    unless identifier
      index += 1
      next
    end
    identifier_start = index
    index = finish
    token_property = TOKEN_PROPERTIES[identifier]
    next unless token_property

    preceding = identifier_start - 1
    preceding -= 1 while preceding >= 0 && expression_space?(source.getbyte(preceding))
    next if preceding >= 0 && source.getbyte(preceding) == 46

    accessor = skip_expression_space(source, index)
    if source.getbyte(accessor) == 46
      property_start = skip_expression_space(source, accessor + 1)
      property, property_end = read_identifier(source, property_start)
      return true unless property
      return true if property == token_property

      index = property_end
    elsif source.getbyte(accessor) == 91
      kind, property, property_end =
        static_bracket_property(source, accessor + 1)
      return true if kind == :dynamic || property == token_property

      index = property_end
    else
      return true
    end
  end
  false
end

def github_token_reference?(value)
  return false unless value.is_a?(String)

  actions_expression_bodies(value).any? do |expression|
    token_access_in_expression?(expression)
  end
end

def token_in_environment?(node)
  case node
  when Hash
    node.any? do |key, value|
      in_this_environment =
        key == "env" &&
        value.is_a?(Hash) &&
        value.values.any? do |environment_value|
          github_token_reference?(environment_value)
        end
      in_this_environment || token_in_environment?(value)
    end
  when Array
    node.any? { |value| token_in_environment?(value) }
  else
    false
  end
end

def shell_command_receives_token?(node)
  case node
  when Hash
    node.any? do |key, value|
      risky_run =
        key == "run" &&
        github_token_reference?(value)
      risky_run || shell_command_receives_token?(value)
    end
  when Array
    node.any? { |value| shell_command_receives_token?(value) }
  else
    false
  end
end

workflows.each do |relative_path, workflow|
  next unless workflow_event?(workflow, "pull_request_target")

  warn "#{relative_path}: pull_request_target is not allowed"
  exit 1
end

workflows.each do |relative_path, workflow|
  next unless token_in_environment?(workflow)

  warn "#{relative_path}: GitHub token must not be written to an environment variable"
  exit 1
end

# Stronger, explicit policy: shell steps may not reference a GitHub token at
# all. This avoids guessing whether an executable was downloaded in this step
# or in an earlier step of the same job.
workflows.each do |relative_path, workflow|
  next unless shell_command_receives_token?(workflow)

  warn "#{relative_path}: GitHub token references are not allowed in shell run commands"
  exit 1
end

if workflow_event?(required_workflow, "schedule")
  warn "#{required_path}: Repository policy must not run on schedule"
  exit 1
end

[
  "pull_request",
  "push",
  "workflow_dispatch"
].each do |event_name|
  unless workflow_event_present?(required_workflow, event_name)
    warn "#{required_path}: missing required event: #{event_name}"
    exit 1
  end
end

["pull_request", "push"].each do |event_name|
  next if workflow_event_branches_include_main_without_negative_patterns?(required_workflow, event_name)

  warn "#{required_path}: #{event_name} branches must include main without negative patterns"
  exit 1
end

if workflow_event?(external_workflow, "pull_request")
  warn "#{external_path}: External links must not run on pull_request"
  exit 1
end

if workflow_event?(external_workflow, "push")
  warn "#{external_path}: External links must not run on push"
  exit 1
end
