# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Make the source importable for autodoc as modules land in the repo.
sys.path.insert(0, os.path.abspath(os.path.join('..', '..')))
sys.path.insert(0, os.path.abspath(os.path.join('..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join('..', '..', 'test')))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'GisFIRE'
copyright = '2026, Jaume Figueras'
author = 'Jaume Figueras'
release = '0.9'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
]

# -- Intersphinx: link cross-references to external projects' docs -----------
# Lets roles like :class:`~sqlalchemy.orm.DeclarativeBase` resolve to the
# upstream documentation. Inventories are fetched at build time, so the build
# needs network access (or a cached objects.inv).
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'sqlalchemy': ('https://docs.sqlalchemy.org/en/20', None),
}
intersphinx_timeout = 15

templates_path = ['_templates']
exclude_patterns = []

language = 'en'

highlight_language = 'default'
pygments_style = 'sphinx'
autodoc_member_order = 'bysource'  # keep attribute/function order from the source

# NOTE: once the SQLAlchemy models are ported, register a custom autodoc
# documenter for `hybrid_property` here (as in GisFIRE2) so hybrid properties are
# documented like normal @property attributes. Left out for now to keep the docs
# build free of a hard SQLAlchemy import.

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
