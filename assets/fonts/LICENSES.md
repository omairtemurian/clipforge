# Font licenses

The caption fonts (SPEC 6.9), all under the SIL Open Font License 1.1
(OFL), https://openfontlicense.org. The OFL lets these fonts be bundled and
redistributed with software as long as each copy keeps the copyright notice
and license; it reserves no font names for these files. Each font's license
text sits next to it, unchanged from the upstream copy. Montserrat, Inter
and Noto Emoji were downloaded on 2026-10-31, Vazirmatn and Noto Sans
Hebrew on 2026-11-01.

## Montserrat-ExtraBold.ttf

- Font: Montserrat ExtraBold (family "Montserrat ExtraBold", weight 800),
  version 9.000, designed by Julieta Ulanovsky.
- Source: https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf
  (repository https://github.com/JulietaUla/Montserrat).
- SHA-256: `d3ac6a843d3ba6d5cafd44cf39e437055c8aed7e261010f595f57d3c7b3e2c1b`
  (455,468 bytes).
- Copyright 2011 The Montserrat Project Authors
  (https://github.com/JulietaUla/Montserrat).
- License: OFL 1.1, `Montserrat-OFL.txt` (the repository's `OFL.txt`).
- Changes: none.
- Used by the karaoke_bold, boxed, neon and comic caption templates.

## Inter-Bold.ttf

- Font: Inter Bold (family "Inter", full name "Inter Bold", weight 700),
  version 4.001, designed by Rasmus Andersson.
- Source: `extras/ttf/Inter-Bold.ttf` of the Inter 4.1 release,
  https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip.
- SHA-256: `288316099b1e0a47a4716d159098005eef7c0066921f34e3200393dbdb01947f`
  (420,428 bytes).
- Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter).
- License: OFL 1.1, `Inter-OFL.txt` (`LICENSE.txt` of the release).
- Changes: none.
- Used by the minimal and clean_subtitle caption templates.

## NotoEmoji-VariableFont_wght.ttf

- Font: Noto Emoji (family "Noto Emoji"), version 3.002, a monochrome emoji
  font with a weight axis (300 to 700, 400 by default), by Google.
- Source: https://raw.githubusercontent.com/google/fonts/main/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf
  (Google Fonts' copy of https://github.com/googlefonts/emoji-bw).
- SHA-256: `de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551`
  (1,982,596 bytes).
- Copyright 2013 Google LLC.
- License: OFL 1.1, `NotoEmoji-OFL.txt` (Google Fonts'
  `ofl/notoemoji/OFL.txt`).
- Changes: none to the font. The file is renamed from `NotoEmoji[wght].ttf`
  to the name Google Fonts gives it in its downloads, which keeps brackets
  (special characters in shells, URLs and ffmpeg filter arguments) out of
  file names.
- Used for the emoji of `backend/clipforge/captions_templates/emoji_map.yaml`:
  libass finds no fallback font for emoji, so captions draw them in this font.
  Also used for the `emoji:<emoji>` overlays of Pro Edit
  (`backend/clipforge/proedit/overlays/procedural.py`, drawn with Pillow).

## Vazirmatn-Bold.ttf

- Font: Vazirmatn Bold (family "Vazirmatn", full name "Vazirmatn Bold",
  weight 700), version 33.003, designed by Saber Rastikerdar: a Persian and
  Arabic font (Arabic script with Latin letters).
- Source: `fonts/ttf/Vazirmatn-Bold.ttf` of the v33.003 release,
  https://github.com/rastikerdar/vazirmatn/releases/download/v33.003/vazirmatn-v33.003.zip
  (repository https://github.com/rastikerdar/vazirmatn).
- SHA-256: `f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723`
  (123,036 bytes).
- Copyright 2015 The Vazirmatn Project Authors
  (https://github.com/rastikerdar/vazirmatn).
- License: OFL 1.1, `Vazirmatn-OFL.txt` (`OFL.txt` of the release).
- Changes: none.
- Used for caption text in Arabic script (Persian, Arabic, Urdu) when the
  caption's font has no glyphs for it (`clipforge.fonts.covering_font`),
  such as captions translated into Persian or Arabic (SPEC-v2 3.4).

## NotoSansHebrew-Bold.ttf

- Font: Noto Sans Hebrew Bold (family "Noto Sans Hebrew", full name "Noto
  Sans Hebrew Bold", weight 700), version 3.001, by the Noto Project: Hebrew
  with Latin letters (the release's `full` build; its `hinted` and
  `unhinted` builds have Hebrew only).
- Source: `NotoSansHebrew/full/ttf/NotoSansHebrew-Bold.ttf` of the
  NotoSansHebrew-v3.001 release,
  https://github.com/notofonts/hebrew/releases/download/NotoSansHebrew-v3.001/NotoSansHebrew-v3.001.zip
  (repository https://github.com/notofonts/hebrew).
- SHA-256: `96f88305d31a8432f0fe6648c853cb9ef77db8e52ada8948ed0c577037d45423`
  (66,608 bytes).
- Copyright 2022 The Noto Project Authors (https://github.com/notofonts/hebrew);
  the font's name table says 2024.
- License: OFL 1.1, `NotoSansHebrew-OFL.txt` (`OFL.txt` of the release).
- Changes: none.
- Used for Hebrew caption text when the caption's font has no glyphs for
  it (`clipforge.fonts.covering_font`): Vazirmatn has no Hebrew.

## Display fonts from Google Fonts (TASK-199)

Thirteen display and sans fonts for the caption templates, downloaded on
2026-11-01 unchanged from the official Google Fonts repository,
https://github.com/google/fonts at commit
`6c1dbe27dcf7d817d4b62cec033ba77fa8e2a5ec` (the `ofl/<family>/` or
`apache/<family>/` directory named in each URL; each family's METADATA.pb
says its license). Eleven are under the SIL Open Font License 1.1 (OFL), two
(Luckiest Guy, Permanent Marker) under the Apache License 2.0; both allow
bundling and redistribution with the copyright notice and license kept next
to the font, which the license file of each row is (the upstream copy,
unchanged). No font was changed and none reserves its name against this use.
Fonts with a non-commercial, freeware or unclear license are not bundled
(SPEC-v2 1.3).

| Font file | Family (libass name) | Version | License | License file | Source (under raw.githubusercontent.com/google/fonts/main/) | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `Poppins-Black.ttf` | Poppins Black | 4.004 | OFL 1.1 | `Poppins-OFL.txt` | `ofl/poppins/Poppins-Black.ttf` | `d82aaaf98a9283f9a8edd24e51173337d8eaf09e25cd3d98831f8ec8461748a1` |
| `Anton-Regular.ttf` | Anton | 2.116 | OFL 1.1 | `Anton-OFL.txt` | `ofl/anton/Anton-Regular.ttf` | `a4ba3a92350ebb031da0cb47630ac49eb265082ca1bc0450442f4a83ab947cab` |
| `BebasNeue-Regular.ttf` | Bebas Neue | 2.000 | OFL 1.1 | `BebasNeue-OFL.txt` | `ofl/bebasneue/BebasNeue-Regular.ttf` | `08e4623805102d819f58601e46e345648846075e363b2ceb23313c2d1c83ec73` |
| `Bangers-Regular.ttf` | Bangers | 2.100 | OFL 1.1 | `Bangers-OFL.txt` | `ofl/bangers/Bangers-Regular.ttf` | `4160a7311de9342674cce9160cde9fcbb30f48190397d86ff1b70b455af65824` |
| `ArchivoBlack-Regular.ttf` | Archivo Black | 1.006 | OFL 1.1 | `ArchivoBlack-OFL.txt` | `ofl/archivoblack/ArchivoBlack-Regular.ttf` | `dd9a89a019b4849f66ab75455fe7bdf931311042cbb0f0f97acc061539703180` |
| `LilitaOne-Regular.ttf` | Lilita One | 1.002 | OFL 1.1 | `LilitaOne-OFL.txt` | `ofl/lilitaone/LilitaOne-Regular.ttf` | `f5b641c45c69d772ee4eda687bc9fda411d5cad6b0b45371491da4580cbc8d59` |
| `TitanOne-Regular.ttf` | Titan One | 1.001 | OFL 1.1 | `TitanOne-OFL.txt` | `ofl/titanone/TitanOne-Regular.ttf` | `563ff6de179bbd44bcd7d2a6c448d6dc3bf935834237cf1250e506e65cd86ff1` |
| `Bungee-Regular.ttf` | Bungee | 2.000 | OFL 1.1 | `Bungee-OFL.txt` | `ofl/bungee/Bungee-Regular.ttf` | `c4f5361ce120af3e6b9156d0bf379fa19cda2ea0cd18ac01fd99596c6bf66e3f` |
| `PassionOne-Black.ttf` | Passion One Black | 1.002 | OFL 1.1 | `PassionOne-OFL.txt` | `ofl/passionone/PassionOne-Black.ttf` | `c954dbac8835bf16f938f8d97fe1627d47aa122d60246169ff55cec772949e96` |
| `Righteous-Regular.ttf` | Righteous | 1.000 | OFL 1.1 | `Righteous-OFL.txt` | `ofl/righteous/Righteous-Regular.ttf` | `2ffb3fe5c27d7e6571210b800448c4e234e651b46c6b4426c1bb567e5341348a` |
| `Staatliches-Regular.ttf` | Staatliches | 1.000 | OFL 1.1 | `Staatliches-OFL.txt` | `ofl/staatliches/Staatliches-Regular.ttf` | `8395212aa4c6c3534bd39a745d956305ff080c3f3ed73ba61e4fbaae951e55cc` |
| `LuckiestGuy-Regular.ttf` | Luckiest Guy | 1.001 | Apache 2.0 | `LuckiestGuy-LICENSE.txt` | `apache/luckiestguy/LuckiestGuy-Regular.ttf` | `cfbdd68a039f92df51cf3721506af6242e64594c6325fe0bedbeff3fe385d980` |
| `PermanentMarker-Regular.ttf` | Permanent Marker | 1.001 | Apache 2.0 | `PermanentMarker-LICENSE.txt` | `apache/permanentmarker/PermanentMarker-Regular.ttf` | `28f82c8a7943cb8e9d599f8554da1d4fc75dbcf69b9885ad6c0611d20c6946c5` |

Copyright notices (the fonts' name tables): Poppins, Anton, Archivo Black,
Bangers, Bebas Neue, Bungee and Staatliches: "The <family> Project
Authors"; Lilita One: 2011 Juan Montoreano; Titan One: 2011 Rodrigo
Fuenzalida; Passion One: 2011 Fontstage; Righteous and Luckiest Guy: 2011 and
2010 Brian J. Bonislawsky DBA Astigmatic (AOETI); Permanent Marker: 2010
Font Diner, Inc.

## UI font: Poppins (TASK-200)

The web UI's typeface (not a caption font, so it lives outside this folder
in `frontend/public/fonts/`, served by the app itself with `@font-face`; no
CDN). Four weights downloaded on 2026-11-02 unchanged from
https://github.com/google/fonts at commit
`6c1dbe27dcf7d817d4b62cec033ba77fa8e2a5ec` (`ofl/poppins/`), version 4.004,
Copyright 2020 The Poppins Project Authors
(https://github.com/itfoundry/Poppins), OFL 1.1. The license file
`frontend/public/fonts/Poppins-OFL.txt` is Google Fonts' `ofl/poppins/OFL.txt`
(identical to `Poppins-OFL.txt` here). No changes; no reserved font name.

| Font file (under `frontend/public/fonts/`) | Weight | License | Source (under raw.githubusercontent.com/google/fonts/main/) | SHA-256 |
| --- | --- | --- | --- | --- |
| `Poppins-Regular.ttf` | 400 | OFL 1.1 | `ofl/poppins/Poppins-Regular.ttf` | `7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba` |
| `Poppins-Medium.ttf` | 500 | OFL 1.1 | `ofl/poppins/Poppins-Medium.ttf` | `90373e7d838d32468438fc3e152dca0bdb12edcab99ea639f158790b1ba1fd05` |
| `Poppins-SemiBold.ttf` | 600 | OFL 1.1 | `ofl/poppins/Poppins-SemiBold.ttf` | `d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286` |
| `Poppins-Bold.ttf` | 700 | OFL 1.1 | `ofl/poppins/Poppins-Bold.ttf` | `983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c` |
