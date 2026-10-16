"""Windows launcher checks. Docker branches use a stub; local mode starts the real API."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(os.name == 'nt', 'Windows batch launcher')
class LauncherTest(unittest.TestCase):
    def docker_case(self, *, compose=0, info=0, desktop=False, ready=False, up=0):
        with tempfile.TemporaryDirectory(prefix='jana-bat-') as directory:
            root = Path(directory)
            shutil.copy(ROOT / 'START.bat', root / 'START.bat')
            log, flag = root / 'docker.log', root / 'ready'
            desktop_path = root / 'programfiles/Docker/Docker/Docker Desktop.exe'
            if desktop:
                desktop_path.parent.mkdir(parents=True)
                desktop_path.touch()
            (root / 'docker.cmd').write_text('''@echo off
>>"%JANA_DOCKER_LOG%" echo %*
if "%~1 %~2"=="compose version" exit /b %MOCK_COMPOSE%
if "%~1 %~2"=="compose up" exit /b %MOCK_UP%
if exist "%MOCK_READY_FILE%" exit /b 0
exit /b %MOCK_INFO%
''', encoding='ascii')
            (root / 'powershell.cmd').write_text('''@echo off
>>"%JANA_DOCKER_LOG%" echo DesktopStart %*
if "%MOCK_START_READY%"=="1" type nul >"%MOCK_READY_FILE%"
exit /b 0
''', encoding='ascii')
            (root / 'timeout.cmd').write_text('@exit /b 0\n', encoding='ascii')
            env = {**{key:value for key,value in os.environ.items() if key.upper() not in {'PROGRAMFILES','LOCALAPPDATA'}}, 'PATH':str(root)+os.pathsep+os.environ['PATH'],
                   'PROGRAMFILES':str(root/'programfiles'), 'LOCALAPPDATA':str(root/'local'),
                   'JANA_NO_PAUSE':'1', 'JANA_DOCKER_LOG':str(log), 'MOCK_READY_FILE':str(flag),
                   'MOCK_COMPOSE':str(compose), 'MOCK_INFO':str(info), 'MOCK_UP':str(up),
                   'MOCK_START_READY':'1' if ready else '0'}
            env['JANA_DOCKER_DESKTOP'] = str(desktop_path) if desktop else ''
            result = subprocess.run([os.environ['COMSPEC'],'/d','/c','START.bat --docker'],cwd=root,env=env,capture_output=True,text=True,timeout=30)
            return result, log.read_text() if log.exists() else ''

    def test_running_docker_starts_compose(self):
        result, log = self.docker_case()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('compose up --build', log)
        self.assertNotIn('DesktopStart', log)

    def test_stopped_desktop_is_started_before_compose(self):
        result, log = self.docker_case(info=1, desktop=True, ready=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('DesktopStart', log)
        self.assertIn('-WindowStyle Hidden', log)
        self.assertLess(log.index('DesktopStart'), log.index('compose up'))

    def test_missing_compose_reports_failure(self):
        result, log = self.docker_case(compose=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Compose is unavailable', result.stdout)
        self.assertNotIn('compose up', log)

    def test_unavailable_engine_does_not_start_compose(self):
        result, log = self.docker_case(info=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('engine is not running', result.stdout)
        self.assertNotIn('compose up', log)

    def test_desktop_timeout_stops_with_error(self):
        result, log = self.docker_case(info=1, desktop=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('120 seconds', result.stdout)
        self.assertNotIn('compose up', log)

    def test_compose_build_error_is_not_reported_as_success(self):
        result, _ = self.docker_case(up=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Startup failed', result.stdout)

    def test_real_local_mode(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port=listener.getsockname()[1]
        with tempfile.TemporaryFile() as output:
            env={**os.environ,'JANA_NO_PAUSE':'1','JANA_PORT':str(port)}
            process=subprocess.Popen([os.environ['COMSPEC'],'/d','/c','START.bat --local'],cwd=ROOT,env=env,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as response:
                            self.assertEqual(response.status,200)
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=1) as response:
                            self.assertIn(b'Jana Address',response.read())
                        break
                    except OSError:
                        if process.poll() is not None:
                            output.seek(0)
                            self.fail(output.read().decode(errors='replace'))
                        time.sleep(.1)
                else:
                    self.fail('Local server failed to start')
            finally:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                process.wait(timeout=10)

    def test_explicit_docker_mode_without_installation(self):
        if shutil.which('docker') or (Path(os.environ['PROGRAMFILES'])/'Docker/Docker/resources/bin/docker.exe').exists():
            self.skipTest('Docker is installed on this machine')
        result=subprocess.run([os.environ['COMSPEC'],'/d','/c','START.bat --docker'],cwd=ROOT,env={**os.environ,'JANA_NO_PAUSE':'1'},capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Docker was not found',result.stdout)


if __name__ == '__main__':
    unittest.main()
