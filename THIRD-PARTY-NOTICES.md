# Third-party notices

TextCAD is built on other people's work. This file lists it and says, for each
piece, which licence it is under.

**Where these facts come from.** Every licence below was read from the
installed package's own metadata (`importlib.metadata`, i.e. the `METADATA` and
`LICENSE` files inside the installed distribution) on 2026-09-16, or from the
project's own licence file where the package ships one. None of it is from
memory. The versions named are the ones TextCAD is developed against; a newer
install can carry a different licence, so re-read the metadata before a
release. The regeneration command is at the bottom of this file.

This file lists what TextCAD *uses*. It does not say what TextCAD itself is
licensed under — that is not decided yet, and there is deliberately no
`LICENSE` file in this repository.

---

## 1. Shipped inside this repository

One third-party library is copied into the repo and served to the browser, so
it travels with every copy of TextCAD.

| What | Version | Licence | Where |
|---|---|---|---|
| **three.js** (WebGL viewport) | r160 (0.160.0) | MIT | `static/vendor/three/0.160.0/` |

Copyright © 2010-2023 three.js authors. The full MIT text is in
`static/vendor/three/0.160.0/LICENSE`, exactly as shipped by the project.
Only three files are vendored: the core module and the two add-ons the
viewport imports (`OrbitControls.js`, `STLLoader.js`).

MIT asks one thing: keep the copyright notice and the licence text with the
code. That is what the `LICENSE` file beside it is for — do not delete it.

---

## 2. The geometry kernel — read this one

This is the only dependency whose licence has real consequences for how
TextCAD may be distributed, so it gets its own section.

| What | Version | Licence |
|---|---|---|
| **build123d** (the modelling API TextCAD writes against) | 0.11.1 | Apache-2.0 |
| **cadquery-ocp-novtk** (a.k.a. **OCP** — the Python bindings) | 7.9.3.1.1 | Apache-2.0 |
| **cadquery-ocp-proxy** | 7.9.3.1.1 | Apache-2.0 |
| **Open CASCADE Technology (OCCT)** — the C++ kernel inside those bindings | 7.9.x, bundled in the OCP wheel | **LGPL-2.1, with the Open CASCADE Exception 1.0** |

build123d's own `NOTICE` records that it began as a derivative of CadQuery,
also Apache-2.0.

**About OCCT.** The `cadquery-ocp-novtk` wheel declares Apache-2.0, but that
covers the *binding* code that pywrap generates. The wheel also contains 70
native libraries — the `TK*.dll` files are OCCT itself. OCCT is published by
Open CASCADE SAS under LGPL-2.1 plus its own additional exception; both texts
are in the OCCT repository (`LICENSE_LGPL_21.txt`,
`OCCT_LGPL_EXCEPTION.txt`), and the exception reads, in part:

> As a special exception to the GNU Lesser General Public License version 2.1,
> you may distribute such object code incorporating material from header files
> provided with the Open CASCADE Technology libraries ... under terms of your
> choice, provided that you give prominent notice in supporting documentation
> to this code that it makes use of or is based on facilities provided by the
> Open CASCADE Technology software.

So: **this notice is the "prominent notice" the exception asks for.** TextCAD
makes use of and is based on facilities provided by the Open CASCADE
Technology software.

In practice, for TextCAD as it stands today:

- TextCAD *calls* OCCT through a Python import. It does not statically link it
  and it does not modify it. That is the arrangement LGPL is written to allow,
  whatever licence TextCAD itself ends up under.
- If a future release ever bundles a **modified** OCCT, the modified kernel
  must stay LGPL and its source must be available. Shipping OCCT unmodified,
  as pip installs it, carries no such obligation on TextCAD's own code.
- If TextCAD is ever sold or shipped in a form where the user cannot replace
  the kernel library, that is the point to take proper advice. Open CASCADE
  SAS also sells a commercial licence for exactly this case.

The OCP wheel additionally bundles third-party native libraries that OCCT's
data exchange and imaging use: FreeImage, FreeType, OpenEXR/Imath/Iex/
IlmThread, libjpeg, libpng, libtiff, libwebp/libsharpyuv, LittleCMS (lcms2),
OpenJPEG, OpenJPH, LERC, LibRaw, liblzma, libdeflate, zlib and zstd, plus the
Microsoft C++ runtime redistributables. Each carries its own permissive or
LGPL-style licence from its own project. TextCAD neither ships nor calls them
directly — they arrive inside the OCP wheel — but a binary release that
bundles the wheel should reproduce their notices too.

---

## 3. Installed by `requirements.txt`

| Package | Version | Licence |
|---|---|---|
| build123d | 0.11.1 | Apache-2.0 (see section 2) |
| fastapi | 0.140.0 | MIT |
| uvicorn | 0.51.0 | BSD-3-Clause |
| openai | 2.46.0 | Apache-2.0 |
| anthropic | 0.117.0 | MIT |
| mcp | 1.28.1 | MIT |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 (the OpenCV library itself; the wheel also ships `LICENSE-3RD-PARTY.txt` for what OpenCV bundles) |
| numpy | 2.5.1 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pytest | 9.1.1 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| watchfiles | 1.2.0 | MIT |

`pytest` and `httpx` are test-only; `watchfiles` is used by `dev.py` only.

---

## 4. Brought in by those

These are not named in `requirements.txt` — pip installs them because
something above needs them. All permissive.

**MIT:** anyio, annotated-types, attrs, executing, h11, httpx-sse, iniconfig,
jedi, jiter, jsonschema, jsonschema-specifications, parso, pluggy, pure_eval,
pydantic, pydantic-core, pydantic-settings, referencing, rpds-py, six,
stack-data, trianglesolver, urllib3, wcwidth, charset-normalizer,
svgelements, svgpathtools, ezdxf.

**BSD (2- or 3-clause):** click, colorama, decorator, httpcore, idna, ipython,
joblib, matplotlib-inline, mpmath, prompt_toolkit, Pygments, python-dotenv,
scikit-learn, scipy, sse-starlette, starlette, sympy, threadpoolctl,
traitlets, webcolors, websockets.

**Apache-2.0:** anytree, asttokens, distro, ocp_gordon, ocpsvg,
python-multipart, requests.

**Other:** `certifi` — MPL-2.0. `tqdm` — MPL-2.0 AND MIT. `sniffio` — MIT OR
Apache-2.0. `packaging` — Apache-2.0 OR BSD-2-Clause. `typing_extensions` —
PSF-2.0. `lib3mf` — BSD. `python-dateutil` — dual BSD / Apache-2.0.
`pywin32` (Windows only) — PSF.

Nothing in this list is copyleft for TextCAD's own code. `certifi` and `tqdm`
are MPL-2.0, which is file-level copyleft: it binds only those packages' own
files, which TextCAD does not modify.

---

## 5. Not third-party

The AI models TextCAD can call (Anthropic, OpenAI/OpenRouter) are services
reached over the network, not code shipped here. The `openai` and `anthropic`
packages above are just their client libraries. Nothing in this repository
carries a model's weights or a provider's terms.

The UI uses the operating system's own fonts (Segoe UI / system-ui). No font
files are shipped.

---

## Regenerating this file

```powershell
C:\Python314\python.exe -c "import importlib.metadata as md; [print(d.metadata['Name'], d.version, d.metadata.get('License-Expression') or d.metadata.get('License') or [c for c in (d.metadata.get_all('Classifier') or []) if c.startswith('License')]) for d in md.distributions()]"
```

Check three.js against `static/vendor/three/0.160.0/LICENSE`, and OCCT against
`LICENSE_LGPL_21.txt` and `OCCT_LGPL_EXCEPTION.txt` in the OCCT repository.
