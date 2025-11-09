"""
Maya-side wrapper for calling splatter-image inference in separate conda environment.
Uses the existing inference_local.py script via subprocess.
"""

import subprocess
import os
import sys
import re


class SplatterSubprocessInference:
    """
    Wrapper that calls splatter-image inference via subprocess.

    Uses the existing inference_local.py script in the splatter-image conda environment.
    """

    def __init__(self, conda_env_name='splatter-image', splatter_repo_path=None):
        """
        Args:
            conda_env_name: Name of conda environment with splatter-image
            splatter_repo_path: Path to splatter-image repository
        """
        self.conda_env_name = conda_env_name

        # Auto-detect splatter-image path
        if splatter_repo_path is None:
            # Assume it's in the parent directory of maya_plugin
            maya_plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.splatter_repo_path = os.path.join(
                os.path.dirname(maya_plugin_dir),
                'splatter-image'
            )
        else:
            self.splatter_repo_path = splatter_repo_path

        self.inference_script = os.path.join(self.splatter_repo_path, 'inference_local.py')

        # Validate paths
        if not os.path.exists(self.splatter_repo_path):
            raise FileNotFoundError(f"Splatter-image repository not found: {self.splatter_repo_path}")
        if not os.path.exists(self.inference_script):
            raise FileNotFoundError(f"Inference script not found: {self.inference_script}")

        print(f"[SplatterSubprocess] Initialized")
        print(f"  Conda env: {self.conda_env_name}")
        print(f"  Splatter repo: {self.splatter_repo_path}")
        print(f"  Inference script: {self.inference_script}")

    def run_inference(self, image_path, output_ply_path, remove_bg=True, fg_ratio=0.65,
                     progress_callback=None):
        """
        Run inference via subprocess using inference_local.py.

        Args:
            image_path: Path to input image
            output_ply_path: Where to save the PLY file
            remove_bg: Whether to remove background
            fg_ratio: Foreground ratio (0.5-0.85)
            progress_callback: Optional callback(progress_percent, message)

        Returns:
            str: Path to generated PLY file

        Raises:
            RuntimeError: If inference fails
        """
        # Ensure absolute paths
        image_path = os.path.abspath(image_path)
        output_ply_path = os.path.abspath(output_ply_path)

        # inference_local.py saves to {output_dir}/mesh.ply
        # So we need to specify the output directory, not the full PLY path
        output_dir = os.path.dirname(output_ply_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # The actual PLY will be saved here
        actual_ply_path = os.path.join(output_dir, "mesh.ply")

        # Build command - handle Windows + WSL case
        import platform
        is_windows = platform.system() == 'Windows'

        if is_windows:
            # Running Maya on Windows, but conda env is in WSL
            # Need to convert Windows paths to WSL paths and prefix with 'wsl'
            print("[SplatterSubprocess] Detected Windows - calling WSL...")

            # Convert Windows paths to WSL paths
            # C:\Users\... -> /mnt/c/Users/...
            def win_to_wsl_path(win_path):
                # Handle UNC paths (\\wsl$\...)
                if win_path.startswith('\\\\wsl'):
                    # Extract the Linux path from UNC
                    parts = win_path.split('\\')
                    # \\wsl$\Ubuntu\root\... -> /root/...
                    if len(parts) > 3:
                        return '/' + '/'.join(parts[4:])
                # Handle regular drive paths
                if len(win_path) > 1 and win_path[1] == ':':
                    drive = win_path[0].lower()
                    rest = win_path[2:].replace('\\', '/')
                    return f'/mnt/{drive}{rest}'
                return win_path.replace('\\', '/')

            wsl_image_path = win_to_wsl_path(image_path)
            wsl_output_dir = win_to_wsl_path(output_dir)
            wsl_inference_script = win_to_wsl_path(self.inference_script)

            print(f"  Windows image path: {image_path}")
            print(f"  WSL image path: {wsl_image_path}")
            print(f"  WSL output dir: {wsl_output_dir}")
            print(f"  WSL inference script: {wsl_inference_script}")

            # For WSL, activate conda environment and run directly
            # Using conda activate instead of conda run to avoid segfault issues
            conda_init = "source /root/miniconda3/etc/profile.d/conda.sh"
            conda_activate = f"conda activate {self.conda_env_name}"
            python_cmd = f"python {wsl_inference_script} --input {wsl_image_path} --output {wsl_output_dir} --foreground-ratio {fg_ratio}"

            if not remove_bg:
                python_cmd += " --no-remove-bg"

            # Combine all commands
            conda_cmd = f"{conda_init} && {conda_activate} && {python_cmd}"
            cmd = ['wsl', 'bash', '-c', conda_cmd]
        else:
            # Running on Linux/Mac - normal conda command
            cmd = [
                'conda', 'run', '-n', self.conda_env_name, '--no-capture-output',
                'python', self.inference_script,
                '--input', image_path,
                '--output', output_dir,
                '--foreground-ratio', str(fg_ratio)
            ]

        if not remove_bg:
            cmd.append('--no-remove-bg')

        print(f"[SplatterSubprocess] Running command:")
        print(f"  {' '.join(cmd)}")

        if progress_callback:
            progress_callback(10, "Starting inference process...")

        try:
            # Run subprocess
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                text=True,
                cwd=self.splatter_repo_path,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )

            if progress_callback:
                progress_callback(20, "Loading model...")

            # Read output line by line for progress updates
            output_lines = []
            for line in iter(process.stdout.readline, ''):
                if line:
                    line = line.rstrip()
                    output_lines.append(line)
                    print(f"  [inference] {line}")

                    # Parse progress from output
                    if progress_callback:
                        if "Loading model" in line or "loading model" in line.lower():
                            progress_callback(30, "Loading model...")
                        elif "Preprocessing" in line or "preprocessing" in line.lower():
                            progress_callback(40, "Preprocessing image...")
                        elif "Running model" in line or "inference" in line.lower():
                            progress_callback(50, "Running inference...")
                        elif "Rendering" in line or "rendering" in line.lower():
                            progress_callback(70, "Rendering preview...")
                        elif "Saved PLY" in line or "mesh.ply" in line:
                            progress_callback(90, "Saving outputs...")

            # Wait for completion
            process.wait()

            if progress_callback:
                progress_callback(95, "Processing results...")

            # Check return code
            if process.returncode != 0:
                raise RuntimeError(
                    f"Inference failed with return code {process.returncode}\n"
                    f"Output:\n" + "\n".join(output_lines)
                )

            # Check if PLY was created
            if not os.path.exists(actual_ply_path):
                raise RuntimeError(
                    f"PLY file not created at expected location: {actual_ply_path}\n"
                    f"Output:\n" + "\n".join(output_lines)
                )

            # If user specified a different PLY name, rename it
            if output_ply_path != actual_ply_path:
                import shutil
                shutil.move(actual_ply_path, output_ply_path)
                final_path = output_ply_path
            else:
                final_path = actual_ply_path

            if progress_callback:
                progress_callback(100, "Inference complete!")

            print(f"[SplatterSubprocess] Success! PLY saved to: {final_path}")
            return final_path

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Inference error: {str(e)}")

    def test_connection(self):
        """Test if the conda environment and dependencies are accessible"""
        try:
            import platform
            is_windows = platform.system() == 'Windows'

            print("[SplatterSubprocess] Testing conda environment...")
            if is_windows:
                print("  (Running on Windows, calling into WSL...)")

            # Test 1: Check conda environment exists
            if is_windows:
                test_cmd = "source /root/miniconda3/etc/profile.d/conda.sh && conda env list"
                cmd = ['wsl', 'bash', '-c', test_cmd]
            else:
                cmd = ['conda', 'env', 'list']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if self.conda_env_name not in result.stdout:
                print(f"  ❌ Conda environment '{self.conda_env_name}' not found!")
                print(f"  Available environments:")
                print(result.stdout)
                return False
            else:
                print(f"  ✓ Found conda environment '{self.conda_env_name}'")

            # Test 2: Check PyTorch
            if is_windows:
                test_cmd = f"source /root/miniconda3/etc/profile.d/conda.sh && conda activate {self.conda_env_name} && python -c 'import torch; print(f\"PyTorch {{torch.__version__}} - CUDA available: {{torch.cuda.is_available()}}\")'"
                cmd = ['wsl', 'bash', '-c', test_cmd]
            else:
                cmd = [
                    'conda', 'run', '-n', self.conda_env_name,
                    'python', '-c',
                    'import torch; print(f"PyTorch {torch.__version__} - CUDA available: {torch.cuda.is_available()}")'
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                print(f"  ✓ {result.stdout.strip()}")
            else:
                print(f"  ❌ PyTorch check failed: {result.stderr}")
                return False

            # Test 3: Check if inference script exists
            if os.path.exists(self.inference_script):
                print(f"  ✓ Found inference script: {os.path.basename(self.inference_script)}")
            else:
                print(f"  ❌ Inference script not found: {self.inference_script}")
                return False

            print("[SplatterSubprocess] ✓ All tests passed!")
            return True

        except subprocess.TimeoutExpired:
            print("[SplatterSubprocess] ❌ Test timed out")
            return False
        except Exception as e:
            print(f"[SplatterSubprocess] ❌ Test error: {e}")
            return False


# Convenience function for Maya
def create_inference_engine(conda_env='splatter-image', splatter_path=None):
    """
    Create a subprocess-based inference engine.

    Usage in Maya:
        from splatter_subprocess import create_inference_engine
        engine = create_inference_engine()

        # Test it
        engine.test_connection()

        # Run inference
        ply_path = engine.run_inference(
            'input.jpg',
            'output.ply',
            remove_bg=True,
            fg_ratio=0.65
        )

    Args:
        conda_env: Name of conda environment with splatter-image
        splatter_path: Optional path to splatter-image repo (auto-detected if None)
    """
    return SplatterSubprocessInference(
        conda_env_name=conda_env,
        splatter_repo_path=splatter_path
    )
