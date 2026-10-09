KFS wildfire history download (South Korea)
===========================================

Fetches *산불발생이력* (wildfire occurrence history) — the Korea Forest Service (산림청)
record of every South Korean wildfire — from the *생활안전지도* (Safemap) open API of the
Ministry of the Interior and Safety, service ``IF_0088``, to a GeoJSON file on disk. It
touches no database.

Usage
-----

.. code-block:: console

   # how many records there are — one request, downloads nothing
   python3 -m src.apps.download.wildfires.south_korea_kfs.download_wildfires count

   # the whole history in one file
   python3 -m src.apps.download.wildfires.south_korea_kfs.download_wildfires all \
       --output-dir ~/data/south_korea

The service key is read from ``SAFEMAP_SERVICE_KEY`` (put it in ``.env``) or from
``--service-key``. It is never written to the log, the GeoJSON or the sidecar.

Getting a key that works
------------------------

The dataset page is
`safemap.go.kr … objtId=207 <https://www.safemap.go.kr/opna/data/dataViewRenew.do?objtId=207>`_,
and it is in Korean. Two steps, and the second is easy to miss:

1. **인증키 발급** (key issuance), under *개발자센터 → 오픈API → 인증키 발급*. This gives
   a key of the form ``XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXX``.
2. **사용신청** (usage application), the button on the dataset page itself. Safemap
   authorises a key *per API*; until this is approved the key is answered with result
   code 30, ``SERVICE_KEY_IS_NOT_REGISTERED_ERROR`` (등록되지 않은 서비스키) — the same
   answer a made-up key gets. The approval shows under *오픈API My Data*.

The page warns that businesses handling location data need a location-based-service
registration certificate (위치기반서비스사업신고필증) or the application may be rejected.
That is aimed at companies; for research, state the purpose in the application.

What the API offers
-------------------

``IF_0088`` takes ``serviceKey``, ``pageNo``, ``numOfRows`` and ``returnType`` and
**nothing else**: no year, no region, no sort order. So there is no ``year`` mode; the
whole history comes down, and the records-per-year table is printed at the end and kept in
the sidecar. The page says the data is updated yearly.

Every field is a string, and is written as served:

=============================================  ============================================
Field                                          Meaning
=============================================  ============================================
``occu_date``                                  ignition date, ``YYYYMMDD``
``occu_year`` ``occu_mt`` ``occu_de``          its parts — zero-padded in some years only
``occu_tm`` / ``occu_day``                     ignition time ``HHMM`` / weekday (Korean)
``end_year`` ``end_mt`` ``end_de`` ``end_tm``  when the fire was put out
``adres`` / ``rn_adres``                       lot-number / road-name address
``resn``                                       cause, free Korean text
``ar`` / ``amount``                            burnt area (ha) / damage (won)
``ctprvn_cd`` ``sgg_cd`` ``emd_cd``            province / municipality / neighbourhood code
``x`` / ``y``                                  location, **EPSG:3857** (Web Mercator metres)
``objt_id``                                    serial number
=============================================  ============================================

The page does not say what ``x``/``y`` are; they are Web Mercator, which the sample rows on
the page confirm — each lands on its own address. The GeoJSON geometry is the WGS84 point
converted from them (the spherical Mercator inverse, exact for EPSG:3857), and ``x``/``y``
stay in the properties untouched. Points that land outside South Korea are counted and
reported, which is how a change of coordinate system on the service would show up.

Errors come back as HTTP 500
----------------------------

An application error — bad key, missing parameter — is HTTP **500** with an ordinary JSON
body whose ``header.resultCode`` says what went wrong. The client reads that code before
the status and retries only the transient ones (01, 02, 04, 05); a refused key, an
exhausted quota (22) or an expired key (31) stop the run at once with a message saying
what to do.

Being a polite client
---------------------

* ``--page-size`` (default 500). No ceiling is documented, so every page is checked: if
  the server returns fewer rows than asked for while more remain, it is clamping, paging by
  ``pageNo`` would skip records, and the run stops and says to lower ``--page-size``.
* ``--delay`` seconds between the start of one request and the next (default 1).
* Retries with exponential backoff, for transient failures only.
* A ``User-Agent`` naming GisFIRE.

Before writing, the download is checked against ``totalCount`` and for repeated
``objt_id`` — without a sort order, a dataset changing mid-run would shift rows across
pages — and nothing is written if either check fails. An existing file is left alone
unless ``--overwrite`` is passed.

Output
------

``south_korea_kfs_wildfires_all.geojson`` and ``south_korea_kfs_wildfires_all.meta.json``.
The sidecar records the endpoint, the page size, the expected and written counts, the
records per year, how many records lack a location, the coordinate systems and the
licence.

.. warning::

   The data is licensed **KOGL Type 4** (공공누리 제4유형): attribution required, **no
   commercial use, no derivative works**. Analysis and figures with attribution are fine;
   redistributing a modified copy of the dataset is not.

Reference
---------

.. automodule:: src.apps.download.wildfires.south_korea_kfs.download_wildfires
   :members:
