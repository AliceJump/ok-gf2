import os


def count_lines_of_code(folder_path, extensions=None):
    total_lines = 0
    extensions = extensions or [".py", ".cpp", ".h", ".js", ".html"]  # Specify file types to count

    for root, _, files in os.walk(folder_path):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, encoding="utf-8") as f:
                        lines = f.readlines()
                        total_lines += len(lines)
                        print(f"{file}: {len(lines)} lines")
                except Exception as e:
                    print(f"Could not read {file_path}: {e}")

    print(f"\nTotal lines of code: {total_lines}")
    return total_lines


# Example usage
folder_path = r"src"  # Replace with the folder path
count_lines_of_code(folder_path)

import sys

from PySide6.QtCore import QLocale


def get_language_fallbacks(locale_name: str) -> list[str]:
    """
    Generates a fallback list for a given locale name like 'en_US'.

    Returns a list ordered:
    1. The original locale_name (e.g., 'en_US').
    2. The base language code (e.g., 'en').
    3. Other potential locales for that language (e.g., 'en_GB', 'en_AU').
       Note: This relies on iterating through known countries, not system availability.
    """
    # Use QLocale to parse the input and get language enum
    input_locale = QLocale(locale_name)
    target_language_enum = input_locale.language()

    # Get canonical names using QLocale for consistency
    target_name = input_locale.name()  # e.g., "en_US
    parts = locale_name.split("_")
    base_lang_code = parts[0]

    fallbacks = [locale_name]
    if base_lang_code not in fallbacks:
        fallbacks.append(base_lang_code)

    processed = set(fallbacks)  # Keep track of added names to avoid duplicates

    try:
        all_countries = list(QLocale.Country)

        for country_enum in all_countries:
            # Skip AnyCountry as it would just recreate the base_lang_code
            if country_enum == QLocale.Country.AnyCountry:
                continue

            # Create locale for the target language + current country
            variant_locale = QLocale(target_language_enum, country_enum)
            variant_name = variant_locale.name()  # e.g., "en_GB"

            # Add if it's valid (not C locale) and not already added
            if variant_name not in processed:
                fallbacks.append(variant_name)
                processed.add(variant_name)
    except Exception as e:
        print(f"Warning: Could not iterate through QLocale.Country enums: {e}", file=sys.stderr)
        # Continue without the extra variants if enum iteration fails

    return fallbacks


# Example usage:
target_locale_name = "en_US"
fallbacks = get_language_fallbacks(target_locale_name)
print(f"Fallbacks for {target_locale_name}: {fallbacks}")
# Example output: Fallbacks for en_US: ['en_US', 'en', 'en_GB', 'en_CA', 'en_AU', ...]

target_locale_name = "fr_CA"
fallbacks = get_language_fallbacks(target_locale_name)
print(f"Fallbacks for {target_locale_name}: {fallbacks}")
# Example output: Fallbacks for fr_CA: ['fr_CA', 'fr', 'fr_BE', 'fr_FR', 'fr_CH', ...]

target_locale_name = "de"
fallbacks = get_language_fallbacks(target_locale_name)
print(f"Fallbacks for {target_locale_name}: {fallbacks}")
# Example output: Fallbacks for de: ['de', 'de_DE', 'de_AT', 'de_CH', ...]
