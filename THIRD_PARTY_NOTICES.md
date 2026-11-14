# Third-party notices

Third-party code keeps its original copyright notices and license terms.
This document identifies the Unreal plugin source copies selected for this
repository. It does not replace their license files or license notices embedded
in source headers.

## BlueprintWebsockets / EasyWebsockets

- Source: <https://github.com/minimpoun/BlueprintWebsockets>
- Location: `unreal/Plugins/BlueprintWebsockets-main/`
- Copyright: Copyright (c) 2022 Chris
- License: MIT, supplied in
  [LICENSE](unreal/Plugins/BlueprintWebsockets-main/LICENSE).
- The local descriptor identifies Chris Ringenberg as the creator and targets
  Unreal Engine 5.6.0. Sources, resources, descriptor and original notices are
  included; generated binaries and caches are excluded.

## RuntimeAudioImporter

- Source: <https://github.com/gtreshchev/RuntimeAudioImporter>
- Location: `unreal/Plugins/RuntimeAudioImporter-main/`
- Copyright: Copyright (c) 2024 Georgy Treshchev
- License: MIT, supplied in
  [LICENSE](unreal/Plugins/RuntimeAudioImporter-main/LICENSE).
- This is the open-source plugin copy from the existing project, not a copy of
  the separately distributed Fab product. Existing local compatibility changes,
  including `MINIMP3_FLOAT_OUTPUT=1`, are retained.

The plugin also embeds the following third-party components. Their source
headers and existing license notices are retained.

| Component | Source | License and local notice |
| --- | --- | --- |
| libfvad / WebRTC VAD | <https://github.com/dpirch/libfvad> | BSD-3-Clause; [LICENSE.txt](unreal/Plugins/RuntimeAudioImporter-main/Source/ThirdParty/libfvad/LICENSE.txt). Copyright (c) 2011, The WebRTC project authors; Copyright (c) 2016 Daniel Pirch. |
| libopusfile | <https://github.com/xiph/opusfile> | BSD-3-Clause; [COPYING](unreal/Plugins/RuntimeAudioImporter-main/Source/ThirdParty/opusfile/COPYING). Additional copyright notices are retained in individual source files. |
| dr_flac, dr_wav, dr_mp3 | <https://github.com/mackron/dr_libs> | Public-domain / MIT-0 alternatives as stated in each header. The complete embedded license statements are retained in `Source/ThirdParty/dr_flac.h`, `dr_wav.h` and `dr_mp3.h`. |
| minimp3 | <https://github.com/lieff/minimp3> | CC0/public-domain dedication stated in `Source/ThirdParty/minimp3.h` and `minimp3_ex.h`; the corresponding notice is also embedded in `dr_mp3.h`. |

The libopusfile sources referenced a missing `COPYING` file. A copy of the
upstream license from <https://github.com/xiph/opusfile/blob/master/COPYING>
has been added beside those sources. No runtime code was changed as part of
this license preparation.

## Snapshot provenance

Both plugin copies come from the previously used local Unreal project. The
original snapshot did not record an exact upstream commit. The vendored files
in this repository define the versions used here; the links above identify
their upstream projects. Both were built with Unreal Engine 5.6 during frontend
integration.

## Separately installed components

- NVIDIA ACE plugin packages, local Audio2Face models, and their bundled
  runtime libraries are excluded from the plugin source allowlist. Install
  these separately using the instructions in [docs/unreal.md](docs/unreal.md)
  and retain the terms supplied with those packages. The MIT notice supplied
  for NVIDIA plugin code does not assign that license to every bundled model
  or library.
- BlueprintSerializer is optional, disabled, and excluded from the allowlist.
- Unreal Engine is installed separately. Unreal/MetaHuman assets and other
  third-party content retain their own applicable terms; this plugin inventory
  does not relicense them.
- Python dependencies and downloaded backend models are installed separately;
  they retain the licenses supplied by their respective publishers.

When redistributing these plugin source copies, keep their license files,
source-header notices and applicable third-party notices with them. A license
chosen for this project's own code does not replace those terms.
