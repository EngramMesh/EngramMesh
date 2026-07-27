#!/usr/bin/env ruby
# frozen_string_literal: true

require "yaml"

FORM_ROOT_KEYS = %w[name description title labels assignees body].freeze
BODY_KEYS = %w[type id attributes validations].freeze
BODY_TYPES = %w[markdown input textarea dropdown checkboxes].freeze
ID_PATTERN = /\A[a-zA-Z][a-zA-Z0-9_-]*\z/
ADVISORY_URL =
  "https://github.com/EngramMesh/EngramMesh/security/advisories/new"
CONFIG_ROOT_KEYS = %w[blank_issues_enabled contact_links].freeze
CONTACT_LINK_KEYS = %w[name url about].freeze
ATTRIBUTE_KEYS = {
  "markdown" => %w[value],
  "input" => %w[label description placeholder value],
  "textarea" => %w[label description placeholder value render],
  "dropdown" => %w[label description options multiple default],
  "checkboxes" => %w[label description options]
}.freeze
STRING_ATTRIBUTE_KEYS = %w[description placeholder value render].freeze
SCALAR_SCANNER = Psych::ScalarScanner.new(
  Psych::ClassLoader::Restricted.new([], [])
)

def non_empty_string?(value)
  value.is_a?(String) && !value.strip.empty?
end

def yaml_path(parent, key)
  key.match?(/\A[A-Za-z_][A-Za-z0-9_-]*\z/) ? "#{parent}.#{key}" : "#{parent}[#{key.inspect}]"
end

def canonical_scalar_key(node)
  return node.value if node.quoted
  return SCALAR_SCANNER.tokenize(node.value) unless node.tag

  case node.tag
  when "!binary", "tag:yaml.org,2002:binary"
    node.value.unpack("m").first
  when "!str", "!ruby/string", "tag:yaml.org,2002:str"
    node.value
  when "!float", "tag:yaml.org,2002:float"
    Float(SCALAR_SCANNER.tokenize(node.value))
  else
    SCALAR_SCANNER.tokenize(node.value)
  end
end

def inspect_yaml_ast(node, relative_path, errors, path = "$")
  return unless node

  case node
  when Psych::Nodes::Alias
    diagnostic = "#{relative_path}: YAML aliases are not allowed"
    errors << diagnostic unless errors.include?(diagnostic)
  when Psych::Nodes::Mapping
    seen = {}
    node.children.each_slice(2) do |key_node, value_node|
      unless key_node.is_a?(Psych::Nodes::Scalar)
        errors << "#{relative_path}: unsupported non-scalar mapping key at #{path}"
        inspect_yaml_ast(key_node, relative_path, errors, "#{path}<key>")
        inspect_yaml_ast(value_node, relative_path, errors, path)
        next
      end

      source_key = key_node.value
      canonical_key = canonical_scalar_key(key_node)
      child_path = yaml_path(path, source_key)
      if seen.key?(canonical_key)
        errors << "#{relative_path}: duplicate mapping key at #{child_path}"
      else
        seen[canonical_key] = true
      end
      inspect_yaml_ast(key_node, relative_path, errors, "#{child_path}<key>")
      inspect_yaml_ast(value_node, relative_path, errors, child_path)
    end
  when Psych::Nodes::Sequence
    node.children.each_with_index do |child, index|
      inspect_yaml_ast(child, relative_path, errors, "#{path}[#{index}]")
    end
  else
    Array(node.children).each do |child|
      inspect_yaml_ast(child, relative_path, errors, path)
    end
  end
end

def validate_string_attributes(attributes, prefix, errors)
  STRING_ATTRIBUTE_KEYS.each do |key|
    next unless attributes.key?(key)
    next if attributes[key].is_a?(String)

    errors << "#{prefix}.#{key} must be a string"
  end
end

def validate_dropdown(attributes, prefix, errors)
  options = attributes["options"]
  unless options.is_a?(Array) && !options.empty?
    errors << "#{prefix}.options must be a non-empty sequence"
  end

  first_option_indexes = {}
  option_values = options.is_a?(Array) ? options : []
  option_values.each_with_index do |option, index|
    unless non_empty_string?(option)
      errors << "#{prefix}.options[#{index}] must be a non-empty string"
      next
    end
    if first_option_indexes.key?(option)
      errors << "#{prefix}.options[#{index}] duplicates options[#{first_option_indexes[option]}]: #{option}"
    else
      first_option_indexes[option] = index
    end
  end

  if attributes.key?("multiple") &&
      ![true, false].include?(attributes["multiple"])
    errors << "#{prefix}.multiple must be Boolean"
  end

  return unless attributes.key?("default")

  default = attributes["default"]
  unless options.is_a?(Array) &&
      default.instance_of?(Integer) &&
      default >= 0 &&
      default < options.length
    errors << "#{prefix}.default must be a zero-based option index"
  end

  if option_values.any? { |option| option.is_a?(String) && %w[none n/a].include?(option.downcase) }
    errors << "#{prefix}.default cannot be combined with a None or n/a option"
  end
end

def validate_checkboxes(attributes, prefix, errors)
  options = attributes["options"]
  unless options.is_a?(Array) && !options.empty?
    errors << "#{prefix}.options must be a non-empty sequence"
    return
  end

  options.each_with_index do |option, index|
    option_prefix = "#{prefix}.options[#{index}]"
    unless option.is_a?(Hash)
      errors << "#{option_prefix} must be a mapping"
      next
    end
    unknown_keys = option.keys - %w[label required]
    unknown_keys.each do |key|
      errors << "#{option_prefix} has unknown key: #{key}"
    end
    unless non_empty_string?(option["label"])
      errors << "#{option_prefix}.label must be a non-empty string"
    end
    if option.key?("required") && ![true, false].include?(option["required"])
      errors << "#{option_prefix}.required must be Boolean"
    end
  end
end

def validate_attributes(type, attributes, prefix, errors)
  unless attributes.is_a?(Hash)
    errors << "#{prefix} must be a mapping"
    return
  end

  allowed_keys = ATTRIBUTE_KEYS.fetch(type, [])
  (attributes.keys - allowed_keys).each do |key|
    errors << "#{prefix} has unknown key: #{key}"
  end
  validate_string_attributes(attributes, prefix, errors)
  if attributes.key?("label") && !non_empty_string?(attributes["label"])
    errors << "#{prefix}.label must be a non-empty string"
  end

  case type
  when "markdown"
    unless non_empty_string?(attributes["value"])
      errors << "#{prefix}.value must be a non-empty string"
    end
  when "input", "textarea", "dropdown"
    unless attributes.key?("label") || non_empty_string?(attributes["label"])
      errors << "#{prefix}.label must be a non-empty string"
    end
  end

  validate_dropdown(attributes, prefix, errors) if type == "dropdown"
  validate_checkboxes(attributes, prefix, errors) if type == "checkboxes"
end

def validate_validations(item, prefix, errors)
  return unless item.key?("validations")

  validations = item["validations"]
  unless validations.is_a?(Hash)
    errors << "#{prefix}.validations must be a mapping"
    return
  end

  (validations.keys - %w[required]).each do |key|
    errors << "#{prefix}.validations has unknown key: #{key}"
  end
  if validations.key?("required") &&
      ![true, false].include?(validations["required"])
    errors << "#{prefix}.validations.required must be Boolean"
  end
end

def validate_form(document, relative_path, errors)
  (document.keys - FORM_ROOT_KEYS).each do |key|
    errors << "#{relative_path}: unknown root key: #{key}"
  end
  %w[name description].each do |key|
    unless non_empty_string?(document[key])
      errors << "#{relative_path}: #{key} must be a non-empty string"
    end
  end
  if document.key?("title") && !document["title"].is_a?(String)
    errors << "#{relative_path}: title must be a string"
  end
  %w[labels assignees].each do |key|
    next unless document.key?(key)
    value = document[key]
    unless value.is_a?(Array) && value.all? { |entry| non_empty_string?(entry) }
      errors << "#{relative_path}: #{key} must be a sequence of non-empty strings"
    end
  end

  body = document["body"]
  unless body.is_a?(Array) && !body.empty?
    errors << "#{relative_path}: body must be a non-empty sequence"
    return
  end

  unless body.any? { |item| item.is_a?(Hash) && item["type"] != "markdown" }
    errors << "#{relative_path}: body must contain at least one non-Markdown item"
  end

  id_indexes = {}
  body.each_with_index do |item, index|
    prefix = "#{relative_path}: body[#{index}]"
    unless item.is_a?(Hash)
      errors << "#{prefix} must be a mapping"
      next
    end
    (item.keys - BODY_KEYS).each do |key|
      errors << "#{prefix} has unknown key: #{key}"
    end

    type = item["type"]
    unless BODY_TYPES.include?(type)
      errors << "#{prefix}.type is unsupported: #{type}"
      next
    end

    id = item["id"]
    if type != "markdown" || item.key?("id")
      unless id.is_a?(String) && ID_PATTERN.match?(id)
        errors << "#{prefix}.id must match [a-zA-Z][a-zA-Z0-9_-]*"
      else
        if id_indexes.key?(id)
          errors << "#{prefix}.id duplicates body[#{id_indexes[id]}].id: #{id}"
        else
          id_indexes[id] = index
        end
      end
    end

    validate_attributes(
      type,
      item["attributes"],
      "#{prefix}.attributes",
      errors
    )
    validate_validations(item, prefix, errors)
  end
end

def validate_config(document, relative_path, errors)
  (document.keys - CONFIG_ROOT_KEYS).each do |key|
    errors << "#{relative_path}: unknown root key: #{key}"
  end
  unless document["blank_issues_enabled"] == false
    errors << "#{relative_path}: blank_issues_enabled must be false"
  end

  links = document["contact_links"]
  unless links.is_a?(Array)
    errors << "#{relative_path}: contact_links must be a sequence"
    return
  end

  links.each_with_index do |link, index|
    prefix = "#{relative_path}: contact_links[#{index}]"
    unless link.is_a?(Hash)
      errors << "#{prefix} must be a mapping"
      next
    end
    (link.keys - CONTACT_LINK_KEYS).each do |key|
      errors << "#{prefix} has unknown key: #{key}"
    end
    CONTACT_LINK_KEYS.each do |key|
      unless non_empty_string?(link[key])
        errors << "#{prefix}.#{key} must be a non-empty string"
      end
    end
  end

  unless links.any? { |link| link.is_a?(Hash) && link["url"] == ADVISORY_URL }
    errors << "#{relative_path}: contact_links must include #{ADVISORY_URL}"
  end
end

root = File.expand_path(ARGV.fetch(0, File.expand_path("..", __dir__)))
paths = %w[
  .github/ISSUE_TEMPLATE/bug.yml
  .github/ISSUE_TEMPLATE/feature.yml
  .github/ISSUE_TEMPLATE/config.yml
]
errors = []

paths.each do |relative_path|
  path = File.join(root, relative_path)
  begin
    content = File.read(path)
    ast = Psych.parse(content)
    ast_error_count = errors.length
    inspect_yaml_ast(ast, relative_path, errors)
    next if errors.length > ast_error_count

    document = YAML.safe_load(
      content,
      permitted_classes: [],
      permitted_symbols: [],
      aliases: false
    )
    unless document.is_a?(Hash)
      errors << "#{relative_path}: root must be a mapping"
      next
    end
    if relative_path.end_with?("/config.yml")
      validate_config(document, relative_path, errors)
    else
      validate_form(document, relative_path, errors)
    end
  rescue Psych::BadAlias
    alias_diagnostic = "#{relative_path}: YAML aliases are not allowed"
    errors << alias_diagnostic unless errors.include?(alias_diagnostic)
  rescue Psych::Exception
    errors << "#{relative_path}: invalid YAML"
  rescue SystemCallError
    errors << "#{relative_path}: cannot read file"
  end
end

unless errors.empty?
  warn errors.join("\n")
  exit 1
end
