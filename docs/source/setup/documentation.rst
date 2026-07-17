Documentation
=============

.. contents::
   :local:
   :depth: 1

Overview
--------

The documentation is built with `Sphinx <https://www.sphinx-doc.org>`_ using the
`Read the Docs theme <https://sphinx-rtd-theme.readthedocs.io>`_ and Pygments for syntax
highlighting. API pages are generated from docstrings with ``sphinx.ext.autodoc`` and
``sphinx.ext.napoleon`` as modules are ported into the project.

Building
--------

From the project virtual environment::

   make docs

This runs ``sphinx-build`` and writes the HTML output to ``docs/build/html``; open
``docs/build/html/index.html`` to view it.

Configuration
-------------

The Sphinx configuration lives in ``docs/source/conf.py``. It adds the repository root,
``src`` and ``test`` to ``sys.path`` so autodoc can import the code, enables the
autodoc/napoleon extensions and selects the Read the Docs HTML theme.
