$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Join-Path $env:LOCALAPPDATA 'RealVoiceAI'
$Engine = Join-Path $Root 'engine'
$PyDir = Join-Path $Engine 'runtime'
$Python = Join-Path $PyDir 'python.exe'
$Installer = Join-Path $Root 'python-3.12.10-amd64.exe'
$Zip = Join-Path $Root 'rvc-main.zip'
$Tmp = Join-Path $Root 'rvc-extract'
$Log = Join-Path $Root 'engine-install.log'
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Start-Transcript -Path $Log -Append | Out-Null

try {
  Write-Output 'Шаг 1/6: загрузка RVC Real-Time...'
  if (!(Test-Path (Join-Path $Engine 'go-realtime_gui.bat'))) {
    if (Test-Path $Engine) { Remove-Item $Engine -Recurse -Force }
    Invoke-WebRequest -UseBasicParsing 'https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/archive/refs/heads/main.zip' -OutFile $Zip
    if ((Get-Item $Zip).Length -lt 100000) { throw 'Архив RVC слишком маленький или повреждён.' }
    if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force }
    Expand-Archive -LiteralPath $Zip -DestinationPath $Tmp -Force
    $Extracted = Get-ChildItem $Tmp -Directory | Select-Object -First 1
    if (!$Extracted -or !(Test-Path (Join-Path $Extracted.FullName 'realtime_gui.py'))) { throw 'В архиве не найден realtime_gui.py.' }
    Move-Item -LiteralPath $Extracted.FullName -Destination $Engine
    Remove-Item $Tmp -Recurse -Force
  }
  if (!(Test-Path (Join-Path $Engine 'go-realtime_gui.bat'))) { throw 'Не найден go-realtime_gui.bat.' }

  # Patch the upstream isolated-mode flag. With -I, local RVC imports such as
  # tools.file_io are unavailable. Keep the original batch file setup intact.
  $Launcher = Join-Path $Engine 'go-realtime_gui.bat'
  $LauncherText = [System.IO.File]::ReadAllText($Launcher)
  $PatchedLauncherText = $LauncherText.Replace('runtime\python.exe -I realtime_gui.py', 'runtime\python.exe realtime_gui.py')
  if ($PatchedLauncherText -ne $LauncherText) {
    [System.IO.File]::WriteAllText($Launcher, $PatchedLauncherText, (New-Object System.Text.UTF8Encoding($false)))
  }

  Write-Output 'Шаг 2/6: установка изолированного Python 3.12 x64...'
  if (!(Test-Path $Python)) {
    Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $Installer
    $p = Start-Process -FilePath $Installer -ArgumentList @('/quiet','InstallAllUsers=0',"TargetDir=$PyDir",'Include_pip=1','Include_launcher=0','Include_test=0','PrependPath=0','Shortcuts=0') -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Установщик Python завершился с кодом $($p.ExitCode)." }
  }
  if (!(Test-Path $Python)) { throw 'После установки не найден runtime\python.exe.' }

  Write-Output 'Шаг 3/6: обновление pip...'
  & $Python -m pip install --disable-pip-version-check --upgrade pip 'setuptools<81' wheel
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось обновить pip/setuptools/wheel.' }

  Write-Output 'Шаг 4/6: установка PyTorch CUDA 12.8 для RTX 50...'
  & $Python -m pip install --disable-pip-version-check torch==2.7.1+cu128 torchaudio==2.7.1+cu128 --index-url 'https://download.pytorch.org/whl/cu128' --extra-index-url 'https://pypi.org/simple'
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить PyTorch CUDA 12.8.' }

  Write-Output 'Шаг 5/6: установка зависимостей RVC...'
  Push-Location $Engine
  try {
    & $Python -m pip install --disable-pip-version-check --index-url 'https://pypi.org/simple' -r (Join-Path $Engine 'requirments_cu128_py312.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости RVC.' }
  } finally { Pop-Location }

  Write-Output 'Шаг 6/6: загрузка обязательных pretrained-файлов HuBERT и RMVPE...'
  & $Python -m pip install --disable-pip-version-check --upgrade huggingface_hub
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить huggingface_hub.' }
  $Hf = Join-Path $PyDir 'Scripts\hf.exe'
  if (!(Test-Path $Hf)) { throw 'Не найден hf.exe после установки huggingface_hub.' }
  $Assets = Join-Path $Engine 'assets'
  New-Item -ItemType Directory -Force -Path (Join-Path $Assets 'rmvpe') | Out-Null
  & $Hf download lj1995/VoiceConversionWebUI --revision main --include 'hubert_base/*' --local-dir $Assets
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось скачать файлы HuBERT.' }
  & $Hf download lj1995/VoiceConversionWebUI rmvpe.pt --revision main --local-dir (Join-Path $Assets 'rmvpe')
  if ($LASTEXITCODE -ne 0) { throw 'Не удалось скачать веса RMVPE.' }
  if (!(Test-Path (Join-Path $Assets 'hubert_base\config.json')) -or !(Test-Path (Join-Path $Assets 'rmvpe\rmvpe.pt'))) { throw 'Не найдены обязательные файлы HuBERT/RMVPE после скачивания.' }

  Write-Output 'Проверка PyTorch и CUDA...'
  & $Python -c "import torch,sys; print('Torch:', torch.__version__); print('CUDA build:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not detected'); sys.exit(0 if torch.cuda.is_available() else 3)"
  if ($LASTEXITCODE -ne 0) { throw 'PyTorch установлен, но CUDA/GPU не обнаружена. Обнови NVIDIA-драйвер и проверь совместимость.' }
  Write-Output 'Установка RVC завершена. Запусти RVC Real-Time из главного окна.'
} catch {
  Write-Output ('ОШИБКА: ' + $_.Exception.Message)
  Write-Output "Подробный журнал: $Log"
  Stop-Transcript | Out-Null
  exit 1
}
Stop-Transcript | Out-Null
exit 0
