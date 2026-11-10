#!/usr/bin/env python3
import ast
import os
import shutil
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "m30s/img/scripts"
DEXOPT = Path(os.environ.get("STARTUP_DEXOPT_TEST_SOURCE", str(SCRIPTS / "dexopt_all.sh")))

class StartupScriptsTest(unittest.TestCase):
    def run_script(self, source, extra_env=None):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            log = tmp / "commands"
            for name in ("pm", "cmd", "killall", "sleep"):
                command = tmp / name
                command.write_text('#!/bin/sh\nprintf "%s" "' + name + '" >> "$STARTUP_COMMAND_LOG"\n'
                                   'for arg; do printf " <%s>" "$arg" >> "$STARTUP_COMMAND_LOG"; done\n'
                                   'printf "\\n" >> "$STARTUP_COMMAND_LOG"\n'
                                   'exit 0\n')
                command.chmod(0o755)
            env = dict(os.environ, PATH=str(tmp) + os.pathsep + os.environ["PATH"],
                       STARTUP_COMMAND_LOG=str(log))
            env.pop("DEXOPT_FORCE", None)
            env.pop("DEXOPT_RESTART_UI", None)
            env.update(extra_env or {})
            result = subprocess.run(["sh", str(source)], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return log.read_text().splitlines() if log.exists() else []

    def test_automatic_compile_never_restarts_visible_ui(self):
        calls = self.run_script(DEXOPT, {"DEXOPT_FORCE": ""})
        self.assertFalse([x for x in calls if x.startswith("killall")], calls)
        compile_calls = [x for x in calls if x.startswith("cmd")]
        self.assertTrue(any("<package> <compile> <-m> <speed> <com.android.systemui>" in x
                            for x in compile_calls))
        self.assertTrue(any("<package> <compile> <-m> <speed> <-a>" in x
                            for x in compile_calls))

    def test_explicit_manual_compile_can_restart_ui_once(self):
        calls = self.run_script(DEXOPT, {"DEXOPT_FORCE": "", "DEXOPT_RESTART_UI": "1"})
        self.assertEqual([x for x in calls if x.startswith("killall")],
                         ["killall <com.android.systemui> <com.google.android.apps.nexuslauncher>"])

    def test_forced_compile_keeps_existing_no_restart_behavior(self):
        calls = self.run_script(DEXOPT, {"DEXOPT_RESTART_UI": "1"})
        self.assertFalse([x for x in calls if x.startswith("killall")])
        self.assertTrue(any("<-f>" in x for x in calls if x.startswith("cmd")))

    def test_sensor_init_passes_no_shell_variable_to_init(self):
        text = (ROOT / "m30s/img/rc/06_nosensorhog.rc").read_text()
        service = next(line for line in text.splitlines() if line.startswith("service nosensorhog "))
        self.assertEqual(shlex.split(service),
                         ["service", "nosensorhog", "/system/bin/sh", "/system/bin/nosensorhog.sh"])
        self.assertIn("    user shell", text)
        self.assertIn("    group shell", text)
        self.assertIn("    seclabel u:r:shell:s0", text)

    def test_sensor_loop_keeps_exact_three_existing_components(self):
        calls = self.run_script(SCRIPTS / "nosensorhog.sh")
        self.assertEqual(calls, [
            "sleep <30>",
            "pm <disable> <com.google.android.gms/com.google.android.gms.personalsafety.service.PSAService>",
            "pm <disable> <com.google.android.gms/com.google.android.gms.personalsafety.service.PersonalSafetyService>",
            "pm <disable> <com.google.android.gms/com.google.android.gms.personalsafety.service.SndDetectionService>",
        ])

    def image_puts(self, text):
        puts = {}
        for node in ast.walk(ast.parse(text)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "put" and len(node.args) >= 3
                    and isinstance(node.args[1], ast.Constant)):
                puts[node.args[1].value] = (ast.unparse(node.args[0]), ast.literal_eval(node.args[2]))
        return puts

    def assert_startup_wiring(self, text):
        puts = self.image_puts(text)
        self.assertEqual(puts["/system/bin/nosensorhog.sh"],
                         ("os.path.join(HERE, 'scripts', 'nosensorhog.sh')", "755"))
        self.assertEqual(puts["/system/bin/dexopt_all.sh"],
                         ("os.path.join(HERE, 'scripts', 'dexopt_all.sh')", "755"))
        self.assertEqual(puts["/system/bin/firstboot_dexopt.sh"],
                         ("os.path.join(TOOLS, 'firstboot', 'firstboot_dexopt.sh')", "755"))

    def test_checked_in_builder_stages_local_scripts_without_changing_firstboot(self):
        self.assert_startup_wiring((ROOT / "m30s/img/build_a17.py").read_text())

    def test_generator_emits_actual_startup_wiring(self):
        tablet = Path(os.environ.get("STARTUP_TEST_TABLET_REPO",
                                     str(Path(__file__).parent / "testdata/tablet-generator-fixture")))
        with tempfile.TemporaryDirectory() as temp:
            generator = Path(temp) / "make_build_a17.py"
            shutil.copyfile(ROOT / "m30s/img/make_build_a17.py", generator)
            result = subprocess.run(["python3", str(generator), str(tablet)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_startup_wiring((Path(temp) / "build_a17.py").read_text())

    def test_manual_precompile_declares_explicit_ui_restart(self):
        text = (ROOT / "m30s/img/rc/04_precompile.rc").read_text()
        service = next(line for line in text.splitlines() if line.startswith("service precompile "))
        self.assertIn("DEXOPT_RESTART_UI=1", service)
        self.assertIn("DEXOPT_FORCE=", service)

if __name__ == "__main__":
    unittest.main()
