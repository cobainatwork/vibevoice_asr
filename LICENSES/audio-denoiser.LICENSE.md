# Audio-Denoiser-ONNX

Models vendored at `vendor/denoiser/*.onnx` derive from
https://github.com/DakeQQ/Audio-Denoiser-ONNX

## Wrapper License

Apache License 2.0

Copyright (c) 2024 DakeQQ

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Model Licenses

Individual model weights have separate licenses inherited from their respective origins:

- **GTCRN**: Derives from the GTCRN paper (Gated Temporal Convolutional Recurrent Network).
  Original implementation: https://github.com/Xiaobin-Ruan/GTCRN
  License: check upstream repository for current license terms.

- **ZipEnhancer**: Derives from the ZipEnhancer speech enhancement model.
  Original referenced from ModelScope / upstream research.
  License: check upstream repository for current license terms.

Both model weights are used for inference only (not redistributed in this repository).
ONNX files are excluded from git via `vendor/denoiser/.gitignore`.
