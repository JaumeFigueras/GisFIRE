# EGIF — Spanish national wildfire statistics (working notes)

Where the analysis got to on 2026-07-28/30, so it can be picked up cold.

> **Status 2026-07-30 (late): the importer is written and validated on the whole
> archive.** `src/apps/imports/wildfires/egif/` — one app, two steps, Excel then XML:
>
> ```bash
> python3 -m src.apps.imports.wildfires.egif.import_wildfires -d /path/to/egif/
> ```
>
> Validated end to end against the real files: **586,157 fires, campaigns 1982-2023,
> in 141 s** (15 Excel exports + one XML), 0 duplicates, 0 fires without a cause.
> Docs at `docs/source/applications/egif_import_wildfires.rst`; tests under
> `test/apps/imports/wildfires/egif/`. See
> [The importer](#the-importer-as-built).

> **Status 2026-07-30: the model is scoped and closed, checked against the whole
> archive.** All seven XML exports (2004-2023, **248,257 fires**) were profiled
> against the XSD rather than just the 98-fire sample. The scope decision is
> **keep the fire, drop the response and the accounting** — see
> [What the XML carries and what is modelled](#what-the-xml-carries-and-what-is-modelled).
> Revision `c4d81e6b2a97` adds the four code-set arrays and relaxes three
> constraints that the archive proved wrong.

> **Status 2026-07-29 (evening): the data model is built.** `src/providers/egif/`
> holds `EgifIgnition`, `EgifWildfire`, `EgifFireCause`, `EgifFireMotivation` and
> `EgifWildfireReport`, with migrations `7f2c85d43b19` (tables) and `9a3d61c07e84`
> (the `v_egif_ignition` / `v_egif_wildfire` views), tests under
> `test/providers/egif/` and docs under `docs/source/providers/`.
> See [The data model as built](#the-data-model-as-built).

> **Update 2026-07-29 (afternoon): a second export format changes the plan.**
> The portal also exports an **Excel "resumen"** — one flat row per fire, whole country,
> 13,656 rows in a single file. It settles the cause/motivation code lists (§[Excel export])
> and **kills the 100-record assumption** below: exports are blocked at up to 40,000 records
> (XML) / 100,000 (Excel), so a scraping application is not needed. Sections marked
> ~~struck~~ or "**CORRECTED**" were written before that.

**EGIF** = *Estadística General de Incendios Forestales*, the Spanish national fire
statistics. Its unit of record is the **PIF** (*Parte de Incendio Forestal*), the official
fire report form — one per fire. It is an administrative record, **not a perimeter
dataset**: where, when, why, what burnt, and what was sent to fight it.

## Where everything is

| What | Where |
|---|---|
| **Full archive, 1982-2023** | `.../escanya/egif/` — 15 `.xlsx` (4-6 MB) + 15 `.xml` (177-285 MB), spans `1982-1987`, `1988-1990`, `1991-1993`, then 2-3 years each to `2020-2023` |
| Sample XML export (98 fires, Barcelona 2020) | *removed 2026-07-30 when the full archive was downloaded* |
| Sample Excel export (2022+2023, national) | *superseded by `2020-2023.xlsx`* |
| Cause + motivation code lists extracted from it | `NOTES_EGIF_codes.csv` (this repo) |
| Filling instructions (41 pp, v3.6, 9ª actualización) | `.../escanya/egif/instrucciones_parte_incendio_tcm30-512355.pdf` |
| Blank report form (6 pp, 2011 v3) | `.../escanya/egif/parteincendioforestal_web_tcm30-132604.pdf` |
| Portal / statistics page | https://www.miteco.gob.es/es/biodiversidad/temas/incendios-forestales/estadisticas-datos.html |
| Search & download service | https://servicio.mapa.gob.es/incendios/Search/Publico |

## The XML is self-describing

The first ~37 KB of the export is an **inline XSD schema** — every element and type. That
is the structural documentation that is not on the website. Extract it with:

```python
x = open(PATH, encoding='utf-8-sig').read()
open('pif.xsd','w').write(x[x.index('<xsd:schema'):x.index('</xsd:schema>')+13])
```

What the schema does **not** carry is the code lists behind the ~62 `id*` fields. That is
the main gap — see [What is still missing](#what-is-still-missing).

## What the sample export contains

98 fires, **Barcelona province** (`idprovincia=8`), **Catalonia** (`idcomunidad=2`),
**2020**. Report numbers `2020080001`–`2020080098` (year + province + sequence),
consecutive with no gaps, detections spanning 1 Jan to 12 Dec.

~~**The web interface caps a download at 100 records**, so this is page 1 of N — hence the
`_1` suffix in the filename.~~ **CORRECTED.** 100 was the *results-grid page size*
(`cbxNumPaginas`), not the export cap. The export dialog on `Search/Publico` offers a
**block size up to 40,000 records for XML** (default 40,000, `max=50,000`) and **100,000 for
Excel**; the `_1` suffix is the packet number of a multi-packet export. A country-year fits
in one or two packets, so **no pagination scraper is needed** — see [Excel export] and
[How the export actually works].

### Record structure — one `<Pif>`, thirteen blocks plus `ParteMonte`

| Block | Holds |
|---|---|
| `pif_comun` | identity, year, record state |
| `pif_localizacion` | CCAA / province / municipality / comarca codes, *paraje* (free text), UTM (huso, x, y, datum), **latitude/longitude**, MTN sheet + grid |
| `pif_tiempos` | detection; arrival of first ground / aerial / helitransported / coordination resources; controlled; extinguished |
| `pif_deteccion` | who detected it, whether via 112, type of area it started in, what it started next to |
| `pif_causa` | cause, motivation, certainty, investigation, responsibility group, **days since storm** |
| `pif_condiciones` | weather at the fire: station, days since rain, max temp, RH, wind speed/direction, fuel model |
| `pif_propagacion` | fire type (surface / crown / ground) |
| `pif_medios` | personnel, aircraft, heavy machinery, transport, retardant — counts and ownership |
| `pif_tecnicas` | attack type; indirect-attack technique |
| `pif_perdidas` | casualties; burnt area by land ownership |
| `pif_incidencias` | severity index, urban–forest interface, protected areas, ZAR |
| `pif_anexo` | protected spaces affected, regeneration, wildlife, erosion, landscape, economy |
| `ParteMonte` | per forest-unit detail: burnt area by species and vegetation type, canopy cover (FCC), economic valuation |

### There *are* coordinates

Every fire carries a point — both projected and geographic, all 98 populated:

```xml
<huso>31</huso> <x>404147</x> <y>4588697</y> <iddatum>2</iddatum>
<latitud>41.4441304358167</latitud> <longitud>1.85254312549163</longitud>
```

So EGIF fires are mappable as **ignition points**, which is exactly what the ICNF data
lacks. ~~`iddatum=2` is uniform in the sample — confirm what 1/2/3 mean before trusting
the CRS (almost certainly ED50 vs ETRS89 vs WGS84).~~ **Resolved, and the sample was
misleading twice over:** `iddatum` is *absent* from every export before 2014, and the
published `latitud`/`longitud` are computed from `huso`/`x`/`y` rather than measured —
so they are wrong wherever `huso` is. See
[What the archive proved wrong](#what-the-archive-proved-wrong).

### Burnt area reconciles across the two places it is recorded

```
pif_perdidas/RelPerdidaMontePif :  2.52 wooded + 6.14 non-wooded = 8.66 ha (forest)
ParteMonte breakdown            :  2.52 arbolado + 0.45 herbáceo + 5.69 leñoso = 8.66 ha
                                   + 4.06 ha "no forestal"  — SEPARATE, not in the forest total
```

Per fire in the sample: median 0.01 ha, max 1.09 ha. Durations 5 min to 7.9 h, median 1.3 h.

## Cause coding

### Confirmed

`idcausa` is a **three-digit hierarchical code**, first digit = family. In the sample:
`1xx`=8, `2xx`=29, `3xx`=17, `4xx`=31 (all bare `400`), `5xx`=13 (all bare `500`).

**`1xx` = Rayo (lightning), verified empirically**: `pif_causa/diastormenta` (days since the
storm) is non-zero *only* in the `1xx` family — 3 of 8, values 1, 11 and 12 days — and
exactly zero in all 90 other fires. That is a real check, not an assumption, and it means
**EGIF gives lightning attribution plus the holdover interval directly** — directly
relevant to the lightning-fire work.

~~the mapping is almost certainly `100`=Rayo, … `400`=Causa desconocida, `500`=Incendio
reproducido~~ — **CORRECTED by the Excel export**, which prints code *and* label. The real
families are:

| Code | Family | n (2022+2023) |
|---|---|---|
| `100` | Rayo | 1,207 |
| `2xx` | Negligencias — activities *using* fire (agricultural/livestock burns, forestry residue burning, campfires/barbecues, smokers, rubbish burning, clearing) | 2,022 |
| `3xx` | Accidental — activities *without* implicit fire use (railway, power lines, machinery and hand tools, vehicles, military) + `399` other known non-intentional | 1,896 |
| `400` | **Intencionado** (bare, no subcodes; the detail lives in `idmotivacion`) | 7,117 |
| `500` | **Desconocida** | 1,181 |
| `600` | **Reproducido** | 233 |

So `400` is *intentional*, not unknown; unknown is `500`; reproduced is `600` — one family
higher than guessed. The Barcelona-2020 XML sample is consistent with this (31 bare `400`
= intentional, 13 bare `500` = unknown, no `600`).

### The full numeric `idcausa` list is now recovered

**87 distinct cause codes with their official labels**, extracted from the Excel export into
`NOTES_EGIF_codes.csv` (`field,code,label,n_2022_2023`) — together with the 28 motivation
codes. That file is the seed for the `EgifFireCause` / `EgifFireMotivation` lookup tables.

The `2xx`/`3xx` sub-structure matches the prose hierarchy from the PDF, and is finer than
the PDF suggests: e.g. `327` Aerogenerador, `328` Huerto solar/placas solares, `298`
Herraduras de caballo. All twelve `2xx` and eleven `3xx` codes observed in the 2020 sample
appear in the list with labels.

### The `idmotivacion` table is fully recovered (only for intentional fires)

Cross-checked against the export: **`Motivacion` is populated on exactly the 7,117 rows
whose `Causa` is `[400] Intencionado`, and on no others** — so it is strictly a subfield of
the intentional family, as assumed. Every code in the table below appears in the data except
`443`, `461`, `462`; no unlisted codes appear. From the instructions PDF, complete:

| Group | Motivation | Code |
|---|---|---|
| Traditional practices | Agricultural burns escaping to forest | 401 |
| | Livestock burns escaping to forest | 402 |
| | Control of animals damaging crops/livestock | 403 |
| | Clear vegetation in forests under exploitation | 404 |
| | Keep the hill clear, traditional landscape | 405 |
| Hunting | Facilitate hunting | 411 |
| | Hunting conflicts | 412 |
| Fishing | Facilitate fishing | 421 |
| Property | Disputes over ownership of public/private forest | 431 |
| | Force a change of land use | 432 |
| | Alter a property boundary | 433 |
| | Clear forest vegetation on boundaries | 434 |
| Economic gain | Alter timber prices | 441 |
| | Gain (wages, notoriety) from suppression or restoration | 442 |
| | Force the dissolution of *Consorcios*/*Convenios* | 443 |
| | Favour production of forest products (mushrooms, asparagus…) | 444 |
| Protest / disagreement | Create unrest and social alarm | 451 |
| | Animosity toward reforestation | 452 |
| | Rejection of protected natural spaces | 453 |
| Revenge / disputes | Reprisal for reduced public investment in forests | 461 |
| | Resentment over expropriations | 462 |
| | Reprisal for fines imposed | 463 |
| | Revenge | 464 |
| Law enforcement | Distract the Guardia Civil / police | 471 |
| | Draw police/authority attention to a problem | 472 |
| Other | To watch the suppression effort | 481 |
| | Vandalism (*gamberradas*) | 482 |
| | Mentally ill (pyromania and others) | 483 |
| | Pseudo-religious or satanic rites | 484 |
| | Other known motivations | 499 |
| | Unknown motivation | 400 |

Note `400` is a valid value in **both** `idcausa` (unknown cause) and `idmotivacion`
(unknown motivation) — different code spaces, do not merge them.

### Non-intentional cause hierarchy (prose only, no numbers in the PDF)

- **Usos tradicionales del fuego**: quemas agrícolas (rastrojos / restos de poda / restos
  agrícolas) · quemas ganaderas · control de vegetación · trabajos forestales · hogueras y
  barbacoas (hogueras / barbacoas fijas / elementos portátiles / vertidos de brasas y
  cenizas / otras) · otras actividades con uso de fuego · escapes de quemas controladas
  (trabajos preventivos / limpieza de fincas ganaderas / otras) · eliminación de basuras y
  restos (punto ilegal de vertidos / quema puntual / escape de vertedero / restos de poda
  en urbanizaciones / otras)
- **Actividades sin uso implícito de fuego**: ferrocarril (convoy / catenaria / otras) ·
  líneas eléctricas (caída de torreta / rotura de tendido / fauna / vegetación) · motores y
  máquinas · actividades militares · fumadores · otras causas no intencionales · otras
  actividades o usos del monte

Observed `2xx` codes: 212 214 216 221 231 241 243 244 250 292 294 299.
Observed `3xx` codes: 322 323 324 325 326 334 336 337 350 361 363.
The sub-structure clearly matches the prose hierarchy, but the number↔label mapping needs
the official list.

## Enumerations readable from the form's option order

The blank form lists each field's options in order, which very likely equals the id
numbering. **These are hypotheses to verify against the portal's dropdowns, not facts** —
see the two counter-examples below.

| Field | Options in form order |
|---|---|
| `idinvestigacioncausa` | Realizada, No realizada |
| `idcertidumbrecausa` | Cierta, Supuesta |
| `idautorizacionactividad` | No permitida, Autorizada, Sin autorización, No necesaria |
| `idgradoresponsabilidad` | Naturales, Accidente, Negligente, Intencionado, Sin determinar |
| `idcausante` | Identificado, No identificado |
| `idclasedia` | Festivo, Sábado, Laborable víspera festivo, Laborable |
| `iddetectadopor` | Vigilante fijo, Agente forestal, Vigilante móvil, Aeronave, Llamada particular, CC y FF de seguridad, Stmas. automáticos, Base/CDF, Ejército, Otros |
| `idtipoarea` | Área agrícola, ganadera, militar, urbana residencial, urbana industrial, forestal |
| `idiniciadojuntoa` | Excursionistas, Vías férreas, Líneas eléctricas, Vertederos, Autovía/carretera, Pista/camino, Senda, Edificaciones, Otros |
| `idmodelocombustion` | Pastizales, Matorrales, Bosques, Restos |
| `idtipofuego` | De superficie, De copas, De subsuelo |
| `idataque` | Ataque directo, Ataque indirecto |
| `idtipoataqueindirecto` | Cortafuego/líneas de defensa, Contrafuego, Quemas de ensanche |
| `idincidenciaproteccivil` | Cortes de carreteras, de líneas férreas, de suministro eléctrico, de teléfono, Evacuaciones/confinamientos, Daños en edificaciones |
| `idtitularidadmonte` | Demanial, Patrimonial, Privado, Vecinal en mano común, Consorciado/conveniado |

Consistency checks done: `idclasedia` and `idautorizacionactividad` both show exactly
`{1,2,3,4}` in the data, matching four options. Good sign.

**Two counter-examples that prove these need verifying:**

- `idiniciadojuntoa` = **10** appears in the data (with `iniciadojuntootros` = "Ribera del
  río", i.e. the *Otros* free-text), but the 2011 form lists only 9 options. The live
  application has more options than the printed form.
- `idataque` takes `{0,1}` — 0-based — while everything else looks 1-based.

Also note `idnivelgravedadmaximo` is **not** an id: it is the *Índice de Gravedad Potencial*
itself, 0–3 (all 0 in the sample).

## [Excel export] — the flat one-row-per-fire format

Sample: `.../escanya/egif/2022-incendis.xlsx` (2.0 MB, one sheet, **13,656 fire records**).
Despite the filename it holds **two campaigns**: 2022 (8,433) and 2023 (5,223).

### 31 columns, one row per fire

`Campania` · `NumeroParte` · `Estado` · `Comunidad` · `Provincia` · `Municipio` ·
`ComarcaIsla` · `EntidadMenor` · `NumeroMunicipiosAfectados` · `Hoja` · `Cuadricula` ·
`Huso` · `CoordenadaX` · `CoordenadaY` · `Datum` · `NumeroPuntosInicioIncendio` ·
`Detectado` · `Extinguido` · `Causa` · `Motivacion` · `SuperficieArbolada` ·
`SuperficieNoArbolada` · `SuperficieTotalForestal` · `SuperficieAgricola` ·
`OtrasSuperficiesNoforestales` · `AfectoZonasInterfazUrbanoForestal` ·
`TipoInterfazAfectado` · `AfectoEspacioProtegido` · `AfectoTierrasAgrarias` · `AfectoZar` ·
`NumeroPartePss`

Formats: dates `dd/mm/yyyy HH:MM:SS` (naive, local time); areas as **comma-decimal strings**
with 4 dp; booleans as `Si`/`No`; empty cells are `\xa0` / `-` / spaces, not blanks.

### What it gains over the XML

- **Codes come with labels** — `Causa` = `[213]  Quema de restos agrícolas (viñas,etc)`,
  `Datum` = `ETRS89`. This is what closed the cause/motivation gap, and it is worth keeping
  one export purely as the Rosetta stone for the XML's bare ids.
- One file covers the **whole country**, all 17 CCAA / 50 provinces, no province×year slicing.

### What it loses against the XML — the deciding trade-off

- **No numeric INE codes.** `Municipio` / `ComarcaIsla` / `Comunidad` are *names only*
  (uppercase, accented, INE inverted form `MOLAR, EL`, bilingual `KANPEZU/CAMPEZO`). The
  province code survives — `NumeroParte` = `YYYY` + **2-digit INE province** + 4-digit
  sequence, verified 1:1 against the 50 province names — but the join to
  `IgnAdminBoundary.ine_code` at municipality level becomes a `(province, name)` string
  match over 3,816 pairs, including the sentinel `OTRA PROVINCIA`, and 6 names that recur
  across provinces (`MIERES` in Asturias *and* Girona, `CIEZA` in Murcia *and* Cantabria).
  The XML gives `idmunicipio` directly.
- **No `latitud`/`longitud`** — only `Huso`/`CoordenadaX`/`CoordenadaY`/`Datum`, so the point
  must be reprojected. One record has `Huso` = `3` (2022470051, Valladolid; coordinates are
  plainly huso 30) — validate the huso against the province before trusting it.
- **No `diastormenta`** — the days-since-storm holdover interval, the one field flagged as
  directly relevant to the lightning work, is not in the Excel.
- Also dropped: `Controlado` time, `pif_deteccion` (who detected it, 112, area type),
  cause certainty / investigation / responsibility, `pif_condiciones` (weather), fire type,
  `pif_medios` (resources), `pif_tecnicas`, casualties, ownership breakdown, `pif_anexo`,
  and the whole `ParteMonte` species/valuation detail.

### Data quality on the sample

- `SuperficieArbolada + SuperficieNoArbolada = SuperficieTotalForestal` on **all 13,656 rows**.
- `NumeroParte` unique on all rows; `Estado` uniformly `Cerrado Revisión`.
- `Extinguido >= Detectado` everywhere; 211 fires have zero duration; the tail is
  implausible — `2022340108` (Palencia) is stamped exactly 365 days, `2022100291` 141 days
  for 0.10 ha. Real long ones exist too (`2022490141` Zamora / Sierra de la Culebra,
  22,233 ha over 72 days). Treat duration as suspect above ~1 week.
- `Datum` is only ever `ETRS89` (13,609) or `REGCAN95` (47, Canarias) — see gap 3 below.

### Completeness — the caveat that matters

The export is **not** a complete year. Both campaigns are missing whole regions:

| | fires | forest ha | missing CCAA |
|---|---|---|---|
| 2022 | 8,433 | 243,610 | Cantabria, **Navarra** |
| 2023 | 5,223 | 51,858 | Cataluña, Extremadura, Canarias, Ceuta, **Navarra**, … |

Navarra is absent from both. Everything present is `Cerrado Revisión`, so what is missing is
what a region has not yet closed — 2023 is simply still being loaded, and 2022's 243,610 ha
sits below the ~306,000 ha published for that year. **Any year must be re-exported later and
the import must be re-runnable/upsert**, not append-once.

## [How the export actually works]

Verified against the live page (`servicio.mapa.gob.es/incendios/...`), ASP.NET MVC 4 +
jQuery/Kendo, no JS framework:

- Search form `formBusqueda` POSTs multipart to `Search/Publico` with an
  `__RequestVerificationToken` (cookie + hidden field pair) and a static `egif_pin`.
- Export is an **async job**: POST `Search/Public_XmlZip` (or `Search/Public_XlsxZip`) with
  `jsonCriterios` = `{sBusqueda, capitulos, bloque, skip, total, sguid, procesado,
  enpaketado, pakete, tipo}`, poll for `Porcentaje`, then download the ZIP from
  `Search/DescargaZipXml?guid=<guid>&pakete=<n>`. `capitulos` is the 16-flag
  `1|1|1|…` mask of which XML blocks to include.
- **The dropdown lookup endpoints are plain public GETs returning JSON** —
  `ParteIncendioForestal/GetComunidadesAutonomasPublico`,
  `ParteIncendioForestal/ProvinciasByCCAAIdPublico?id=<ccaa>`,
  `ParteIncendioForestal/MunicipiosByProvinciasIdPublico`,
  `ParteIncendioForestal/ComarcasIslasByProvinciaIdPublico`, each
  `[{"Selected":…,"Text":"BARCELONA","Value":"8"}]`. `Value` **is the INE code** (Barcelona 8,
  Girona 17, Lleida 25, Tarragona 43). This is the cheap fix for the Excel's missing
  municipality ids: fetch the four lists once, no scraping app needed.
- The non-`Publico` endpoints (`Search/getCausasIncendio`, `getGrupoCausasIncendio`,
  `getCodEstadoPifs`, `getEspacProtegidos`) **302 to login** — auth-gated, which is why the
  cause list had to come out of the export rather than the form.

## What is still missing

1. ~~**Numeric `idcausa` list.**~~ **DONE** — 87 codes + labels in `NOTES_EGIF_codes.csv`.
2. **Catalogue tables**: `idespecie` (tree species), `idmunicipio` / `idcomarcaisla`,
   `idmodelocombustion` (field variant `RelModeloCombustionCampoPif` uses a wider range),
   `idcatalogomonte`, `idespacioprotegido`, `idmedioaereo`, `idmediopersonalext`,
   `idmediopesado`, `idtitularidadmedio`, `idaprovechamiento`, `idtipoproducto`,
   `idtiporenta`, `idtesela`/`idteselamfe`.
3. ~~**`iddatum`** meaning~~ — **CLOSED 2026-07-30.** `2` = ETRS89, `5` = REGCAN95
   (its 443 occurrences track the huso-28/Canarian fires), `3` = unmappable, 3 records.
   ED50 appears nowhere in 2004-2023; what older campaigns do instead is publish no
   `iddatum` element at all. See
   [What the archive proved wrong](#what-the-archive-proved-wrong).

**Best source for the rest: the portal's own dropdown JSON endpoints** — confirmed public
GETs, see [How the export actually works]. `Value` is the INE code, so
`ign_admin_boundary.ine_code` joins directly; worth verifying against the sample's 69
distinct municipality ids. The auth-gated `Search/get*` endpoints (causes, states, protected
spaces) are not reachable — take those from an Excel export instead.

## Data-quality gotcha found

`pif_condiciones/hora` is unreliable. On record 1 the fire was detected
`2020-01-01T16:30` but the weather observation is stamped `2023-12-18T16:35` — the *time of
day* is right, the *date* is the data-entry date. Use `pif_tiempos/deteccion` for when the
fire happened and treat that field's date as metadata.

## What the XML carries and what is modelled

Profiled on **2026-07-30** across all seven exports (2004-2023, 248,257 fires) by
splitting the inline XSD from the data and counting every element path. Two
findings frame the scope decision:

- The XSD holds **13 `pif_*` blocks + `ParteMonte` + 25 `Rel*` relations**. **Every
  one of the 25 is populated in the real exports** — none of it is dead schema.
  Modelling the lot is ~15 extra tables.
- Only four fields exist in the XSD and are populated in *no* export:
  `notas`, `NumParteEvento`, `ParteMonte/Observaciones`,
  `ParteMonte/ValoracionAmbiental`.

### The decision (2026-07-30): keep the fire, drop the response and the accounting

Driven by the actual purpose — **studying lightning-caused wildfires**. Lightning is
3.8% of 2004-05 rising to 7.1% of 2020-23, order 10-15k fires. Fill rates on that
subset, which is what settled it:

| | 2004-05 | 2020-23 |
|---|---|---|
| `idcausa`=100, cause certainty, MTN sheet, areas | 100% | 100% |
| `diastormenta` (holdover) | 19% | **100%** |
| point, detection/control/extinction, first ground arrival | 81-99% | 98-100% |
| **`RelModeloCombustionPif`** (fuel model), **`RelTipoFuegoPif`** | **100%** | **100%** |
| weather block (rain/temp/RH/wind) | 49-72% | 81-94% |
| `idpeligro` / `probabilidadignicion` | 100% / 81% | **17% / 6%** |

**Added in `c4d81e6b2a97`** — four `text[]` columns on `egif_wildfire_report`. All
twelve pure code-set relations were verified **duplicate-free within a fire** across
29,926 fires, so an array is lossless and saves a join:

| Column | Relation | Why |
|---|---|---|
| `fuel_model_codes` | `RelModeloCombustionPif` | the only record of **what was burning**; 1-4 (pastizal/matorral/bosque/restos) |
| `fire_type_codes` | `RelTipoFuegoPif` | `3` = *de subsuelo*, the smouldering ground fire that makes a holdover physically plausible |
| `start_area_type_codes` | `RelTipoAreaIniciadoPif` | free at that point |
| `started_next_to_codes` | `RelIniciadoJuntoAPif` | pairs with the existing `started_next_to_other` free text |

**Deliberately not modelled**, and why it can wait: `pif_medios` (personnel /
aircraft / machinery, 3 tables), `pif_tecnicas`, `RelVictimaPif`,
`RelPerdidaMontePif`, `RelEspacioProtegidoPif`, `RelTeselaAfectadaPif` (17 fields,
up to **610 rows per fire**), `pif_anexo`'s five regeneration/erosion indices, and
the whole `ParteMonte` tree (26 scalars + 8 sub-relations, incl. the
`RelFactorCalculoPerdida` timber-price chain — heavily used in 2004-05, nearly
abandoned by 2020-23). Also skipped: ~15 block scalars, listed below.

`RelModeloCombustionCampoPif` is **the one deferred item worth reconsidering
first**: it is the *finer* fuel model (14 distinct values against the stored
relation's 4 — a different code space, do not merge), 17,277 rows in 2020-23, but
only 14.5% of lightning fires. One more array column whenever it is wanted.

Two other deferred items with a claim on attention:

- **`RelAsociadoPif`** (438 links in 2020-23, 1,249 in 2004-05) is **EGIF's own
  fire-to-fire relation** — directly relevant to the deferred `WildfireRelation`
  table, and evidence that the vocabulary should be derived rather than guessed.
- **`idpeligro` / `probabilidadignicion`** look ideal (fire-danger index at the
  fire) but availability is **inverted** — near-complete in 2004-05, 17%/6% in
  2020-23. Too patchy to build on.

**Expandability holds** and is why the above is safe to defer: `EgifWildfireReport`
is 1:1 on `EgifWildfire.id`; everything skipped is nullable columns on it or new
tables FK'ing to existing PKs. `report_number` and `egif_id` are unique and stable
and present in both formats, so a re-import backfills by upsert. The one real
constraint: **get column types right first time** — the `v_egif_*` views block
`ALTER COLUMN ... TYPE` on every column they select.

### Block scalars dropped (all cheap to add later)

`idpeligro`, `probabilidadignicion`, `idestadocampaniaprovincia`, `idestadopif`
(code — only the Excel label is stored), `identidadmenor` (code — only the name),
`idvigilantefijo`, `detectadoporotros`, `causaotros`, `motivacionotros`,
`fechadeclaracionnivelmaximo`, `actuaronmediosestatales`, and `pif_anexo`'s
`idporcentajeautoregenerable` / `idefectovidasilvestre` / `idriesgoerosion` /
`idalteracionpaisaje` / `idefectoeneconomia`.

## What the archive proved wrong

Three things the 98-fire sample could not show. All three were **blocking** for any
pre-2014 import and are fixed in `c4d81e6b2a97`.

**1. Nine per cent of the archive has no coordinate.** `ignition_id` was `NOT NULL`.

| | fires | no `x`/`y` | no `huso` |
|---|---|---|---|
| 2004-2005 | 46,888 | 10,865 | 8,872 |
| 2006-2007 | 27,270 | 5,928 | 3,133 |
| 2008-2010 | 39,019 | 5,001 | 4,211 |
| 2011-2013 | 43,208 | 1,037 | 987 |
| 2014-2016 | 30,365 | 24 | 22 |
| 2017-2023 | 61,507 | **0** | 0 |

Total **22,855 of 248,257 (9.2%)**. `x` **never** appears without `huso`, so
`utm_zone` stays `NOT NULL` on the ignition — the rule is simply *no coordinate, no
`egif_ignition` row*, and `v_egif_wildfire` had to become a `LEFT JOIN` or it would
have dropped those fires from the QGIS layer while still looking healthy.

**2. `iddatum` does not exist before 2014, and has three values, not two.** `datum`
was `NOT NULL` and the notes' guess about ED50 was wrong — ED50 appears nowhere in
2004-2023.

- absent entirely in 2004-2013; on 6,401 of 30,365 in 2014-2016; universal from 2017
- values across the whole archive: `2` = 67,462 (ETRS89) · `5` = 443 (tracks the
  Canarian/huso-28 count → REGCAN95) · **`3` = 3 records** (one each in 2014-2016,
  2017-2019, 2020-2023), mapping to nothing published

Hence `datum` nullable, plus a new `datum_code` holding the raw `iddatum` so those
two records keep their code beside a `NULL` label instead of being rounded to
ETRS89. The `CHECK` stays — a `NULL` satisfies `datum IN (...)` in SQL — so an
unknown *label* is still refused while an absent one is allowed.

**3. `huso 3` was not a typo, and the published lat/lon is derived, not
independent.** The `utm_zone IN (28,29,30,31)` CHECK is **dropped**. Seven fires
across 2004-2023 carry a zone outside 28-31 (`3`, `27`, `32`, `33`, `39`, `50`,
`63`, `71`) — and the service's own `latitud`/`longitud` are computed *from* the bad
zone:

```
2011331154  huso 71  x 479930  y 4709201  ->  lat 42.53  lon -117.24   (Pacific)
2011260019  huso 50  x 522617  y 4691013  ->  lat 42.37  lon  117.27   (Mongolia)
2012030039  huso 39  x 766595  y 4291773  ->  lat 38.73  lon   54.07   (Turkmenistan)
```

So **`latitud`/`longitud` cannot be used to validate the projected pair** — they
carry the same error. The importer must derive the zone itself (the province settles
all seven cases) and the column keeps the published number whatever it is; a CHECK
here would only refuse genuine records. This supersedes the earlier note that
`2022470051` was "a typo for 30 that the coordinates themselves disambiguate" — the
coordinates do disambiguate it, but the published lat/lon does not.

## The data model as built

```
DataProvider("EGIF")
│
├── EgifIgnition(Ignition)          ignition.geometry = POINT 4326 (reprojected)
│     report_number (unique) · utm_zone · utm_x · utm_y · datum? · datum_code?
│     start_point_count · mtn_sheet · mtn_grid · place_name
│
├── EgifWildfire(Wildfire)          wildfire.perimeter = NULL, always
│     report_number (unique) · egif_id · campaign · status · ignition_id?
│     ccaa/province/municipality/comarca/minor_entity names
│     province_ine_code · municipality_ine_code · affected_municipality_count
│     cause_id ─► EgifFireCause      motivation_id ─► EgifFireMotivation
│     area_ha_{wooded,non_wooded,forest_total,agricultural,other_non_forest}
│     wui_{affected,compact,scattered,isolated} · protected_space/agricultural/zar
│     └── EgifWildfireReport         1:1 optional — the XML-only blocks
│             control + four response instants · days_since_storm
│             detection / cause-certainty / day-class codes · weather · severity
│             fuel_model_codes · fire_type_codes                    ] text[],
│             start_area_type_codes · started_next_to_codes         ] c4d81e6b2a97
│
└── views: v_egif_ignition · v_egif_wildfire (POINT geometry — see below)
```

`?` marks the columns revision `c4d81e6b2a97` made nullable or added — see
[What the archive proved wrong](#what-the-archive-proved-wrong).

Decisions worth not relitigating:

- **The published coordinate is kept as numbers, not as a geometry in the source CRS.**
  `utm_x`/`utm_y` *are* the original easting and northing, so nothing is lost, and a
  point has no area to compute on a projected grid (unlike `IcnfWildfire`, which keeps
  its polygon in EPSG:3763 for exactly that reason). Keeping the original CRS as a
  geometry would have meant four nullable geometry columns and four more views, because
  the datum and zone vary per row and a geometry column carries one SRID.
- **`v_egif_wildfire` exposes a POINT**, the ignition, not a perimeter — the only
  wildfire view that does. It also carries `has_full_report`, `days_since_storm` and
  the two fuel/behaviour arrays. It **LEFT JOINs the ignition** (since
  `c4d81e6b2a97`): an inner join would drop the 9% of fires with no coordinate out
  of the QGIS layer while the view still looked healthy, which is what
  `test_the_egif_wildfire_view_keeps_a_fire_that_has_no_coordinate` guards.
- **The four multi-valued code lists are `text[]`, not four child tables.** Verified
  duplicate-free within a fire across 29,926 fires, so an array is lossless; the
  relations that carry a *payload* (`RelMedioPersonalPif` and its count,
  `RelEspacioProtegidoPif` and its four areas) could not be flattened this way,
  which is part of why they are out of scope rather than stored badly.
- **`utm_zone` has no CHECK and never should.** The published zone is wrong on seven
  fires and the published lat/lon is wrong with it; deriving the zone is the
  importer's job, not a constraint's.
- **Two catalogue tables, never one.** `400` is *Intencionado* as a cause and
  *Motivación desconocida* as a motivation.
- **`EgifWildfireReport`'s existence is the provenance.** No `source_format` column: a
  fire with a report row has been read from the XML, one without has only ever been in
  an Excel export. `LEFT JOIN ... WHERE r.id IS NULL` resumes a partial import.
- **Perimeters from the autonomous regions will not be written into these rows.** Each
  region becomes its own provider with its own `Wildfire` subclass, related by a
  `WildfireRelation` table — *deliberately not built yet*, because its `kind`
  (`same_event` / `part_of` / `rekindle_of`) and `method` vocabularies should come from
  a real matching exercise rather than a guess. Nothing here depends on it.

## The importer as built

`src/apps/imports/wildfires/egif/` — `readers.py` (the two parsers) and
`import_wildfires.py` (CLI, upserts, catalogues). No `ogr2ogr`, no new dependency:
the `.xlsx` is read straight out of its zip with `ElementTree`, and the only
geometry work is `ST_Transform(ST_SetSRID(ST_MakePoint(x, y), srid), 4326)` in
PostGIS.

**The archive is now 1982-2023** — 15 `.xlsx` + 15 `.xml`, downloaded 2026-07-29/30.
Measured over all 15 Excel exports:

| | |
|---|---|
| fires | **586,157** (campaigns 1982-2023) |
| with a published coordinate | 292,447 |
| **with no coordinate at all** | **293,710 (50.1%)** — every fire before 1998 |
| coordinate refused as implausible | 339 (0.12%) |
| `huso` outside 28-31 | 16 |
| **no detection instant** | **0** — nothing is unstorable |
| cause codes / motivation codes | 87 / 31 |

Design decisions worth not relitigating:

- **Each step writes only the columns its own format publishes.** `XML_WILDFIRE_COLUMNS`
  is deliberately *not* a superset of `EXCEL_WILDFIRE_COLUMNS`. Without this, re-importing
  an Excel export to pick up a revised campaign would null `egif_id`,
  `municipality_ine_code` and the *paraje* — silently. There is a test for exactly that.
- **One transaction per file, bad fires skipped and logged.** A crash mid-file leaves
  nothing; one bad fire does not cost the other 30,000. Only a missing report number or
  a missing detection instant makes a fire unstorable.
- **Excel cells are read by their `r` reference, never by position.** Two fires in
  2008-2010 omit the empty `Extinguido` cell entirely; read positionally every field
  after it shifts one column left and *still parses* — cause becomes extinction time,
  area becomes an interface flag. This is the bug that would never have been noticed.
- **An implausible coordinate is refused, not reprojected.** 339 fires publish a
  northing missing three digits, or the easting in both fields, or an extra digit.
  Stored faithfully they scatter across the ocean; they now get no ignition, like the
  293,710 that never had one. The published numbers survive on the fire's row.
- **A bad `huso` falls back to the province, a good one never does.**
  `PROVINCE_UTM_ZONES` is *modal* and matches the published zone on only 92.7% of
  fires, so letting it override a valid value would move a quarter of a million points.
- **The time zone comes from the province**, not the *comunidad*: EGIF's `idcomunidad`
  is not the INE CCAA code (Cataluña is `2`), while the province code is verifiable
  from `numeroparte` itself.

Known and accepted: **118 of 292,105 stored points (0.04%) fall outside Spain** — mostly
Huesca fires published with `huso 31` and an easting of 750,000-800,000, which belongs to
zone 30. The published zone is *valid*, so it is used as published; correcting it would
mean overriding good published values on a 92.7%-accurate guess. The numbers are stored,
so it stays fixable.

## Next steps

0. ~~**Write the two importers**~~ — **DONE 2026-07-30**, see
   [The importer as built](#the-importer-as-built). All four things the archive check
   called for are handled: the province-derived zone fallback, the assumed ETRS89, no
   ignition row without a coordinate, and `Atlantic/Canary` for the Canarian provinces.
   A fifth was found while validating — the implausible coordinates — and a sixth while
   writing the reader: the omitted Excel cells.
1. ~~**Work out pagination**~~ / ~~build a scraper~~ — **dropped.** Exports are blocked at
   40,000 (XML) / 100,000 (Excel) records, and the whole 2004-2023 archive is already
   downloaded in seven span files of each format.
2. **Pull the four dropdown JSON lists** (CCAA, provincias, municipios, comarcas) into
   lookup tables — one GET each, no scraping app.
3. ~~**Confirm `iddatum`**~~ — **done**, see above.
4. ~~**Then design the model**~~ / ~~**decide how much of the report to keep**~~ —
   **done 2026-07-30**, see
   [What the XML carries and what is modelled](#what-the-xml-carries-and-what-is-modelled).

## Open questions for Jaume

- ~~**Excel or XML as the import source?**~~ **Settled: XML as the data, Excel as the
  code-list reference** (captured in `NOTES_EGIF_codes.csv`). The XML keeps the INE
  municipality ids, the coordinate and `diastormenta`; the Excel is the only public
  source of the cause and motivation labels.
- ~~Is the whole PIF wanted, or only the fire-level subset?~~ **Settled: the fire-level
  subset plus the four fuel/behaviour code lists.** Response and accounting blocks are
  out; `RelModeloCombustionCampoPif` is the first thing to add if that changes.
- Is Spain wanted nationally, or Catalonia only? That changes the download problem by two
  orders of magnitude.
- ~~The sample is one province-year and every fire in it is ≤1.09 ha.~~ **Answered:** no size
  filter is applied — the Excel export carries fires up to 22,233 ha (68 ≥ 500 ha across the
  two campaigns). Barcelona 2020 really
  was that quiet — it affects what "complete" looks like.
