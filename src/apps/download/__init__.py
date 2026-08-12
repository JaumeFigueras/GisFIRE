#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Applications that fetch published data to disk.

The third kind of application in the project, beside ``imports`` and
``statistics``, and the one that touches no database at all.

An importer reads a file that is already on disk; a downloader is what puts it
there. Most providers need none — they publish an archive you fetch once with a
browser — but some publish only through a paged API, where getting a complete
copy means issuing hundreds of requests politely and checking that nothing was
silently truncated. That is a program, and it belongs here rather than inside an
importer that would then be doing two jobs.
"""
