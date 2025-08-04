# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'GisFIRE'
copyright = '2025, Jaume Figueras'
author = 'Jaume Figueras'
release = '0.2'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
]

templates_path = ['_templates']
exclude_patterns = []

highlight_language = 'default'    # or 'python', doesn't affect SQL blocks
pygments_style = 'sphinx'         # or another theme like 'monokai'
pygments_dark_style = "native"    # good for Furo's dark mode
autodoc_member_order = 'bysource' # Keep attrs and functions order when generating the docs

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
