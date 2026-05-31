@echo off
REM Build llama-cpp-python from source with CUDA for GTX 1650 (compute capability 7.5).
REM Uses MSVC 14.44 from VS 2022 BuildTools (compatible with CUDA 12.9; _MSC_VER 1944 < 1950).
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (echo [build] vcvars64 failed & exit /b 1)

set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9"
set "PATH=%CUDA_PATH%\bin;%PATH%"
set "CUDAToolkit_ROOT=%CUDA_PATH%"

set CMAKE_GENERATOR=Ninja
set "CMAKE_ARGS=-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=75"
set FORCE_CMAKE=1

echo [build] nvcc:
nvcc --version
echo [build] cl:
where cl
echo [build] starting pip build...
"C:\Users\Talgat\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe" -m pip install --upgrade --no-cache-dir --force-reinstall --verbose llama-cpp-python
echo [build] EXITCODE=%errorlevel%
