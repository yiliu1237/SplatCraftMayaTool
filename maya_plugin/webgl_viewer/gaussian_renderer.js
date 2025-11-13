/**
 * WebGL-based 3D Gaussian Splatting Renderer
 * Renders Gaussian splats with full attribute support
 */

class GaussianViewer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.gl = this.canvas.getContext('webgl') || this.canvas.getContext('experimental-webgl');

        if (!this.gl) {
            alert('WebGL not supported');
            return;
        }

        // Rendering state
        this.gaussianCount = 0;
        this.buffers = {};
        this.program = null;

        // Camera state (will be updated from Maya)
        this.camera = {
            viewMatrix: this.createIdentityMatrix(),
            projectionMatrix: this.createPerspectiveMatrix(45, 1, 0.1, 10000)
        };

        // Manual control state
        this.manualControlEnabled = true;
        this.syncEnabled = false;  // Bidirectional sync with Maya
        this.manualCamera = {
            position: [0, 0, 100],
            target: [0, 0, 0],
            up: [0, 1, 0],
            yaw: 0,
            pitch: 0,
            distance: 100
        };
        this.keys = {};
        this.mouseDown = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;

        // Performance tracking
        this.frameCount = 0;
        this.lastTime = performance.now();
        this.fps = 0;

        // Grid display
        this.showGrid = true;
        this.gridSize = 100;  // Grid extends from -gridSize to +gridSize
        this.gridSpacing = 10;  // Distance between grid lines
        this.gridBuffers = null;
        this.axisBuffers = null;
        this.showAxis = true;

        // Object transformation (from Maya)
        this.objectTransformMatrix = this.createIdentityMatrix();

        // Initialize
        this.setupWebGL();

        //enable instancing and make a unit quad
        this.extInst = this.gl.getExtension('ANGLE_instanced_arrays');
        if (!this.extInst) {
            console.error('ANGLE_instanced_arrays not available (needed for splats).');
        }
        
        this._initUnitQuad = () => {
        // 2D quad in [-1,1]^2 for billboard impostors
        const verts = new Float32Array([
            -1,-1,   1,-1,   -1, 1,   1, 1
        ]);
        this.buffers = this.buffers || {};
        this.buffers.quad = this.gl.createBuffer();
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, this.buffers.quad);
        this.gl.bufferData(this.gl.ARRAY_BUFFER, verts, this.gl.STATIC_DRAW);
        };
        this._initUnitQuad();


        this.compileShaders();
        this.compileGridShader();
        this.setupCanvas();
        this.setupManualControls();
        this.createGrid();
        this.createAxis();
        this.startRenderLoop();

        this.writeDepth = true;

        console.log('GaussianViewer initialized');
    }

    setupWebGL() {
        const gl = this.gl;

        // Enable features
        gl.enable(gl.DEPTH_TEST);
        this.gl.depthMask(true);

        gl.enable(gl.BLEND);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // premultiplied alpha

        // Make sure both sides of the billboard are visible
        gl.disable(gl.CULL_FACE);

        // Clear color
        gl.clearColor(0.1, 0.1, 0.1, 1.0);
    }

    compileShaders() {
        const gl = this.gl;

        // Vertex shader - transforms Gaussians and computes point size
        const vertexShaderSource = `
            attribute vec2 a_quadPos;     // per-vertex: the unit quad [-1,1]^2
            attribute vec3 a_center;      // per-instance: Gaussian center
            attribute vec4 a_quat;        // per-instance: rotation (normalized)
            attribute vec3 a_scale;       // per-instance: scale (already exp-ed)
            attribute vec3 a_color;       // per-instance
            attribute float a_opacity;    // per-instance

            uniform mat4 u_viewMatrix;
            uniform mat4 u_projectionMatrix;
            uniform mat4 u_objectTransform;  // Object transformation from Maya

            varying vec3 v_color;
            varying float v_opacity;
            varying vec2 v_ex;  // screen-space basis X
            varying vec2 v_ey;  // screen-space basis Y
            varying vec2 v_quadPos;

            mat3 quatToMat3(vec4 q){
                vec3 q2 = q.xyz + q.xyz;
                float xx = q.x * q2.x, yy = q.y * q2.y, zz = q.z * q2.z;
                float xy = q.x * q2.y, xz = q.x * q2.z, yz = q.y * q2.z;
                float wx = q.w * q2.x, wy = q.w * q2.y, wz = q.w * q2.z;
                return mat3(
                    1.0 - (yy + zz), xy + wz,        xz - wy,
                    xy - wz,        1.0 - (xx + zz), yz + wx,
                    xz + wy,        yz - wx,        1.0 - (xx + yy)
                );
            }

            void main(){
                v_quadPos = a_quadPos;
                v_color   = a_color;
                v_opacity = a_opacity;

                // Apply object transformation first, then view
                vec4 centerWorld = u_objectTransform * vec4(a_center, 1.0);
                vec4 centerView = u_viewMatrix * centerWorld;
                vec4 centerClip = u_projectionMatrix * centerView;

                // 3D basis from quat and scales
                vec4 qn = a_quat / max(1e-8, length(a_quat));
                mat3 R = quatToMat3(qn);
                vec3 sx = R[0] * a_scale.x;
                vec3 sy = R[1] * a_scale.y;

                // Apply object transformation rotation to basis vectors
                mat3 objRot = mat3(u_objectTransform);
                sx = objRot * sx;
                sy = objRot * sy;

                // project basis endpoints, derive 2D screen-space basis vectors
                mat3 V = mat3(u_viewMatrix);     // rotation part of view matrix
                vec3 sx_view = V * sx;
                vec3 sy_view = V * sy;

                // project basis endpoints in view space
                vec4 exClip = u_projectionMatrix * vec4(centerView.xyz + sx_view, 1.0);
                vec4 eyClip = u_projectionMatrix * vec4(centerView.xyz + sy_view, 1.0);

                vec2 centerNDC = centerClip.xy / centerClip.w;
                v_ex = exClip.xy / exClip.w - centerNDC;
                v_ey = eyClip.xy / eyClip.w - centerNDC;

                // place the quad around the center using the NDC basis
                vec2 offsetNDC = a_quadPos.x * v_ex + a_quadPos.y * v_ey;
                vec4 pos = centerClip;
                pos.xy += offsetNDC * centerClip.w; // lift back to clip space
                gl_Position = pos;
            }
        `;


        // Fragment shader - renders circular splat with Gaussian falloff
        const fragmentShaderSource = `
            precision mediump float;
            varying vec3 v_color;
            varying float v_opacity;
            varying vec2 v_ex, v_ey;
            varying vec2 v_quadPos;

            void main(){
                // v_quadPos are quad coordinates in [-1,1]^2
                // Approximate Gaussian in the metric induced by (v_ex, v_ey)
                // Map to NDC using the basis; length^2 ~ Mahalanobis distance^2 (approx)
                vec2 p = v_quadPos.x * v_ex + v_quadPos.y * v_ey;

                // Tune factor: 4.0 gives a nice compact footprint; adjust if needed
                float r2 = dot(p, p) * 6.0; // was 4.0
                float alpha = exp(-0.5 * r2) * v_opacity;

                if (alpha < 1e-3) discard;
                gl_FragColor = vec4(v_color * alpha, alpha); // premult-like
            }
        `;

        // Compile shaders
        const vertexShader = this.createShader(gl.VERTEX_SHADER, vertexShaderSource);
        const fragmentShader = this.createShader(gl.FRAGMENT_SHADER, fragmentShaderSource);

        // Link program
        this.program = gl.createProgram();
        gl.attachShader(this.program, vertexShader);
        gl.attachShader(this.program, fragmentShader);
        gl.linkProgram(this.program);

        if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) {
            console.error('Shader program failed to link:', gl.getProgramInfoLog(this.program));
            return;
        }

        // Get attribute and uniform locations
        this.locations = {
            a_quadPos: gl.getAttribLocation(this.program, 'a_quadPos'),
            a_center:  gl.getAttribLocation(this.program, 'a_center'),
            a_quat:    gl.getAttribLocation(this.program, 'a_quat'),
            a_scale:   gl.getAttribLocation(this.program, 'a_scale'),
            a_color:   gl.getAttribLocation(this.program, 'a_color'),
            a_opacity: gl.getAttribLocation(this.program, 'a_opacity'),
            u_viewMatrix: gl.getUniformLocation(this.program, 'u_viewMatrix'),
            u_projectionMatrix: gl.getUniformLocation(this.program, 'u_projectionMatrix'),
            u_objectTransform: gl.getUniformLocation(this.program, 'u_objectTransform')
        };

        console.log('Shaders compiled successfully');
    }

    compileGridShader() {
        const gl = this.gl;

        // Simple vertex shader for grid lines
        const gridVertexShader = `
            attribute vec3 a_position;
            uniform mat4 u_viewMatrix;
            uniform mat4 u_projectionMatrix;

            void main() {
                gl_Position = u_projectionMatrix * u_viewMatrix * vec4(a_position, 1.0);
            }
        `;

        // Simple fragment shader for grid lines
        const gridFragmentShader = `
            precision mediump float;
            uniform vec3 u_color;
            uniform float u_alpha;

            void main() {
                gl_FragColor = vec4(u_color, u_alpha);
            }
        `;

        // Compile shaders
        const vertexShader = this.createShader(gl.VERTEX_SHADER, gridVertexShader);
        const fragmentShader = this.createShader(gl.FRAGMENT_SHADER, gridFragmentShader);

        // Link program
        this.gridProgram = gl.createProgram();
        gl.attachShader(this.gridProgram, vertexShader);
        gl.attachShader(this.gridProgram, fragmentShader);
        gl.linkProgram(this.gridProgram);

        if (!gl.getProgramParameter(this.gridProgram, gl.LINK_STATUS)) {
            console.error('Grid shader program failed to link:', gl.getProgramInfoLog(this.gridProgram));
            return;
        }

        // Get attribute and uniform locations
        this.gridLocations = {
            a_position: gl.getAttribLocation(this.gridProgram, 'a_position'),
            u_viewMatrix: gl.getUniformLocation(this.gridProgram, 'u_viewMatrix'),
            u_projectionMatrix: gl.getUniformLocation(this.gridProgram, 'u_projectionMatrix'),
            u_color: gl.getUniformLocation(this.gridProgram, 'u_color'),
            u_alpha: gl.getUniformLocation(this.gridProgram, 'u_alpha')
        };

        console.log('Grid shader compiled successfully');
    }

    createGrid() {
        const gl = this.gl;

        // Create grid vertices (XZ plane, Y=0)
        const vertices = [];

        // Lines parallel to X axis
        for (let z = -this.gridSize; z <= this.gridSize; z += this.gridSpacing) {
            vertices.push(-this.gridSize, 0, z);
            vertices.push(this.gridSize, 0, z);
        }

        // Lines parallel to Z axis
        for (let x = -this.gridSize; x <= this.gridSize; x += this.gridSpacing) {
            vertices.push(x, 0, -this.gridSize);
            vertices.push(x, 0, this.gridSize);
        }

        this.gridVertexCount = vertices.length / 3;

        // Create buffer
        this.gridBuffers = {
            position: gl.createBuffer()
        };

        gl.bindBuffer(gl.ARRAY_BUFFER, this.gridBuffers.position);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);

        console.log(`Grid created: ${this.gridVertexCount} vertices`);
    }

    createAxis() {
        const gl = this.gl;

        // Create XYZ axis lines
        const axisLength = 20;
        const vertices = [];
        const colors = [];

        // X axis (red)
        vertices.push(0, 0, 0,  axisLength, 0, 0);
        colors.push(1, 0, 0,  1, 0, 0);

        // Y axis (green)
        vertices.push(0, 0, 0,  0, axisLength, 0);
        colors.push(0, 1, 0,  0, 1, 0);

        // Z axis (blue)
        vertices.push(0, 0, 0,  0, 0, axisLength);
        colors.push(0, 0, 1,  0, 0, 1);

        this.axisVertexCount = vertices.length / 3;

        // Create buffers
        this.axisBuffers = {
            position: gl.createBuffer(),
            color: gl.createBuffer()
        };

        gl.bindBuffer(gl.ARRAY_BUFFER, this.axisBuffers.position);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);

        gl.bindBuffer(gl.ARRAY_BUFFER, this.axisBuffers.color);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(colors), gl.STATIC_DRAW);

        console.log('XYZ axes created');
    }

    renderAxis() {
        if (!this.showAxis || !this.gridProgram || !this.axisBuffers) {
            return;
        }

        const gl = this.gl;

        // Use grid shader (it supports colored lines too)
        gl.useProgram(this.gridProgram);

        // Set uniforms
        gl.uniformMatrix4fv(this.gridLocations.u_viewMatrix, false, this.camera.viewMatrix);
        gl.uniformMatrix4fv(this.gridLocations.u_projectionMatrix, false, this.camera.projectionMatrix);

        // Bind position buffer
        gl.bindBuffer(gl.ARRAY_BUFFER, this.axisBuffers.position);
        gl.enableVertexAttribArray(this.gridLocations.a_position);
        gl.vertexAttribPointer(this.gridLocations.a_position, 3, gl.FLOAT, false, 0, 0);

        // Set line width (if supported)
        gl.lineWidth(3);

        // Draw X axis (red)
        gl.uniform3f(this.gridLocations.u_color, 1, 0, 0);
        gl.uniform1f(this.gridLocations.u_alpha, 1.0);  // Fully opaque
        gl.drawArrays(gl.LINES, 0, 2);

        // Draw Y axis (green)
        gl.uniform3f(this.gridLocations.u_color, 0, 1, 0);
        gl.uniform1f(this.gridLocations.u_alpha, 1.0);
        gl.drawArrays(gl.LINES, 2, 2);

        // Draw Z axis (blue)
        gl.uniform3f(this.gridLocations.u_color, 0, 0, 1);
        gl.uniform1f(this.gridLocations.u_alpha, 1.0);
        gl.drawArrays(gl.LINES, 4, 2);

        // Reset line width
        gl.lineWidth(1);

        // Cleanup
        gl.disableVertexAttribArray(this.gridLocations.a_position);
    }

    renderGrid() {
        if (!this.showGrid || !this.gridProgram || !this.gridBuffers) {
            return;
        }

        const gl = this.gl;

        // Use grid shader
        gl.useProgram(this.gridProgram);

        // Set uniforms
        gl.uniformMatrix4fv(this.gridLocations.u_viewMatrix, false, this.camera.viewMatrix);
        gl.uniformMatrix4fv(this.gridLocations.u_projectionMatrix, false, this.camera.projectionMatrix);

        // Grid color - Maya-like gray, semi-transparent
        gl.uniform3f(this.gridLocations.u_color, 0.5, 0.5, 0.5);
        gl.uniform1f(this.gridLocations.u_alpha, 0.3);

        // Bind position buffer
        gl.bindBuffer(gl.ARRAY_BUFFER, this.gridBuffers.position);
        gl.enableVertexAttribArray(this.gridLocations.a_position);
        gl.vertexAttribPointer(this.gridLocations.a_position, 3, gl.FLOAT, false, 0, 0);

        // Draw lines
        gl.drawArrays(gl.LINES, 0, this.gridVertexCount);

        // Cleanup
        gl.disableVertexAttribArray(this.gridLocations.a_position);
    }

    createShader(type, source) {
        const gl = this.gl;
        const shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);

        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            console.error('Shader compilation error:', gl.getShaderInfoLog(shader));
            gl.deleteShader(shader);
            return null;
        }

        return shader;
    }

    loadGaussians(data) {
        const gl = this.gl;

        console.log('Loading Gaussian data:', data);

        // Extract data
        const positions = new Float32Array(data.positions);
        const colors = new Float32Array(data.colors);
        const opacities = new Float32Array(data.opacities);
        const scales = new Float32Array(data.scales);

        let rotations;
        if (data.rotations && data.rotations.length === (positions.length/3)*4) {
            rotations = new Float32Array(data.rotations);
        } else {
            console.warn('No rotations provided; using identity quaternions.');
            const N = positions.length / 3;
            rotations = new Float32Array(4 * N);
            for (let i = 0; i < N; ++i) rotations[i*4 + 3] = 1.0; // (0,0,0,1)
        }


        this.gaussianCount = positions.length / 3;

        console.log(`Data loaded: ${this.gaussianCount} Gaussians`);
        console.log(`  Positions: ${positions.length} floats`);
        console.log(`  Colors: ${colors.length} floats`);
        console.log(`  Opacities: ${opacities.length} floats`);
        console.log(`  Scales: ${scales.length} floats`);

        // Create and upload buffers
        this.buffers.position = this.createBuffer(positions);
        this.buffers.color = this.createBuffer(colors);
        this.buffers.opacity = this.createBuffer(opacities);
        this.buffers.scale = this.createBuffer(scales);
        this.buffers.rotation = this.createBuffer(rotations);

        // Update UI
        document.getElementById('gaussian-count').textContent = this.gaussianCount.toLocaleString();

        console.log(`✓ Loaded ${this.gaussianCount.toLocaleString()} Gaussians to GPU`);
        console.log(`✓ Rendering should begin now...`);
    }



    createBuffer(data) {
        const gl = this.gl;
        const buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
        return buffer;
    }

    updateCameraFromMaya(cameraData) {
        // Only update if sync is enabled
        if (!this.syncEnabled) {
            return;
        }

        // Update view and projection matrices from Maya camera
        this.camera.viewMatrix = new Float32Array(cameraData.viewMatrix);
        this.camera.projectionMatrix = new Float32Array(cameraData.projectionMatrix);

        // Update info display
        document.getElementById('camera-info').textContent = 'Synced';

        // Debug: Log first few camera updates
        if (!this.cameraUpdateCount) this.cameraUpdateCount = 0;
        this.cameraUpdateCount++;

        if (this.cameraUpdateCount <= 5) {
            console.log(`[WebGL] Camera update #${this.cameraUpdateCount}:`, {
                view: cameraData.viewMatrix.slice(0, 4),
                proj: cameraData.projectionMatrix.slice(0, 4)
            });
        }
    }

    setInitialFarCamera(cameraInfo) {
        // Set initial camera position far from scene
        this.manualCamera.position = cameraInfo.position;
        this.manualCamera.target = cameraInfo.target;
        this.manualCamera.distance = cameraInfo.distance;

        // Calculate initial yaw/pitch from position to target
        const dx = cameraInfo.target[0] - cameraInfo.position[0];
        const dy = cameraInfo.target[1] - cameraInfo.position[1];
        const dz = cameraInfo.target[2] - cameraInfo.position[2];

        this.manualCamera.yaw = Math.atan2(dx, dz);
        this.manualCamera.pitch = Math.atan2(dy, Math.sqrt(dx*dx + dz*dz));

        // IMPORTANT: Apply this good view to the actual rendering camera immediately
        // Build view matrix from the manual camera settings
        this.camera.viewMatrix = this.createLookAtMatrix(
            cameraInfo.position,
            cameraInfo.target,
            cameraInfo.up
        );

        // Update projection matrix with correct aspect
        const aspect = this.canvas.width / this.canvas.height;
        this.camera.projectionMatrix = this.createPerspectiveMatrix(45, aspect, 0.1, 10000);

        console.log('[WebGL] Initial far camera set and APPLIED to rendering:', this.manualCamera);
    }

    setupCanvas() {
        // Resize canvas to fill window
        const resize = () => {
            this.canvas.width = this.canvas.clientWidth;
            this.canvas.height = this.canvas.clientHeight;
            this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);

            // Update projection matrix for manual control
            const aspect = this.canvas.width / this.canvas.height;
            this.manualProjection = this.createPerspectiveMatrix(45, aspect, 0.1, 10000);
        };

        window.addEventListener('resize', resize);
        resize();
    }

    setupManualControls() {
        // Keyboard controls
        window.addEventListener('keydown', (e) => {
            const k = e.key;

            // Two-state toggle: occluding vs blended
            if (k === 'o' || k === 'O') {
                this.writeDepth = !this.writeDepth;
                console.log(`[Render] writeDepth = ${this.writeDepth ? 'ON (occluding)' : 'OFF (blended, no depth writes)'}`);
                return; // don't add 'o' to the movement keys map
            }

        this.keys[k.toLowerCase()] = true;
    });


        window.addEventListener('keyup', (e) => {
            const k = e.key;

            // Ignore keyup for the toggle key
            if (k === 'o' || k === 'O') return;

            this.keys[k.toLowerCase()] = false;
        });

        // Mouse controls for rotation
        this.canvas.addEventListener('mousedown', (e) => {
            if (!this.manualControlEnabled) return;
            this.mouseDown = true;
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mouseup', () => {
            this.mouseDown = false;
            this.canvas.style.cursor = 'default';
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.manualControlEnabled || !this.mouseDown) return;

            const deltaX = e.clientX - this.lastMouseX;
            const deltaY = e.clientY - this.lastMouseY;

            // Update angles with sensitivity
            const sensitivity = 0.005;
            this.manualCamera.yaw -= deltaX * sensitivity;
            this.manualCamera.pitch -= deltaY * sensitivity;

            // Clamp pitch to avoid flipping
            this.manualCamera.pitch = Math.max(-Math.PI/2 + 0.01, Math.min(Math.PI/2 - 0.01, this.manualCamera.pitch));

            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;

            // Debug output (first 5 movements)
            if (!this.rotationDebugCount) this.rotationDebugCount = 0;
            if (this.rotationDebugCount < 5) {
                console.log(`[Rotation] Yaw: ${(this.manualCamera.yaw * 180 / Math.PI).toFixed(1)}° Pitch: ${(this.manualCamera.pitch * 180 / Math.PI).toFixed(1)}°`);
                this.rotationDebugCount++;
            }
        });

        // Mouse wheel for zoom
        this.canvas.addEventListener('wheel', (e) => {
            if (!this.manualControlEnabled) return;
            e.preventDefault();

            this.manualCamera.distance *= (1 + e.deltaY * 0.001);
            this.manualCamera.distance = Math.max(1, Math.min(10000, this.manualCamera.distance));
        });
    }

    updateManualCamera() {
        if (!this.manualControlEnabled) return;

        // Update debug display
        if (document.getElementById('yaw-value')) {
            document.getElementById('yaw-value').textContent = (this.manualCamera.yaw * 180 / Math.PI).toFixed(0);
            document.getElementById('pitch-value').textContent = (this.manualCamera.pitch * 180 / Math.PI).toFixed(0);
        }

        const moveSpeed = 5.0;

        // Forward from yaw/pitch
        const cy = Math.cos(this.manualCamera.yaw);
        const sy = Math.sin(this.manualCamera.yaw);
        const cp = Math.cos(this.manualCamera.pitch);
        const sp = Math.sin(this.manualCamera.pitch);

        const forward = [ sy * cp,  sp,  cy * cp ];


        // Flip world-up when upside down to avoid horizon roll
        const upFlip = (cp < 0) ? -1 : 1;
        const upWorld = [0, upFlip, 0];


        // right = normalize(up × f)
        let right = [
            upWorld[1]*forward[2] - upWorld[2]*forward[1],
            upWorld[2]*forward[0] - upWorld[0]*forward[2],
            upWorld[0]*forward[1] - upWorld[1]*forward[0]
        ];
        

        {
            const rl = Math.hypot(right[0], right[1], right[2]) || 1.0;
            right = [ right[0]/rl, right[1]/rl, right[2]/rl ];
        }


        // up = normalize(f × right)
        let up = [
            forward[1]*right[2] - forward[2]*right[1],
            forward[2]*right[0] - forward[0]*right[2],
            forward[0]*right[1] - forward[1]*right[0]
        ];


        {
            const ul = Math.hypot(up[0], up[1], up[2]) || 1.0;
            up = [ up[0]/ul, up[1]/ul, up[2]/ul ];
        }



        // WASD movement
        if (this.keys['w']) {
            this.manualCamera.target[0] += forward[0] * moveSpeed;
            this.manualCamera.target[1] += forward[1] * moveSpeed;
            this.manualCamera.target[2] += forward[2] * moveSpeed;
        }
        if (this.keys['s']) {
            this.manualCamera.target[0] -= forward[0] * moveSpeed;
            this.manualCamera.target[1] -= forward[1] * moveSpeed;
            this.manualCamera.target[2] -= forward[2] * moveSpeed;
        }
        if (this.keys['a']) {
            this.manualCamera.target[0] -= right[0] * moveSpeed;
            this.manualCamera.target[1] -= right[1] * moveSpeed;
            this.manualCamera.target[2] -= right[2] * moveSpeed;
        }
        if (this.keys['d']) {
            this.manualCamera.target[0] += right[0] * moveSpeed;
            this.manualCamera.target[1] += right[1] * moveSpeed;
            this.manualCamera.target[2] += right[2] * moveSpeed;
        }

        // Z/X for up/down
        if (this.keys['z']) {
            this.manualCamera.target[1] += moveSpeed;
        }
        if (this.keys['x']) {
            this.manualCamera.target[1] -= moveSpeed;
        }

        // Calculate camera position from target + distance + angles
        this.manualCamera.position = [
            this.manualCamera.target[0] - forward[0] * this.manualCamera.distance,
            this.manualCamera.target[1] - forward[1] * this.manualCamera.distance,
            this.manualCamera.target[2] - forward[2] * this.manualCamera.distance
        ];

        // Build view matrix
        this.camera.viewMatrix = this.createLookAtMatrix(
            this.manualCamera.position,
            this.manualCamera.target,
            up
        );

        this.camera.projectionMatrix = this.manualProjection;
    }

    startRenderLoop() {
        const render = () => {
            this.updateManualCamera();  // Update manual camera if enabled
            this.render();
            this.updateFPS();
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }


    bindInstanced() {
        const gl = this.gl, ext = this.extInst, loc = this.locations;

        // Per-vertex quad
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.quad);
        gl.enableVertexAttribArray(loc.a_quadPos);
        gl.vertexAttribPointer(loc.a_quadPos, 2, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_quadPos, 0); // per-vertex

        // Per-instance: centers
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.position);
        gl.enableVertexAttribArray(loc.a_center);
        gl.vertexAttribPointer(loc.a_center, 3, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_center, 1);

        // Per-instance: rotations
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.rotation);
        gl.enableVertexAttribArray(loc.a_quat);
        gl.vertexAttribPointer(loc.a_quat, 4, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_quat, 1);

        // Per-instance: scales
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.scale);
        gl.enableVertexAttribArray(loc.a_scale);
        gl.vertexAttribPointer(loc.a_scale, 3, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_scale, 1);

        // Per-instance: colors
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.color);
        gl.enableVertexAttribArray(loc.a_color);
        gl.vertexAttribPointer(loc.a_color, 3, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_color, 1);

        // Per-instance: opacity
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers.opacity);
        gl.enableVertexAttribArray(loc.a_opacity);
        gl.vertexAttribPointer(loc.a_opacity, 1, gl.FLOAT, false, 0, 0);
        ext.vertexAttribDivisorANGLE(loc.a_opacity, 1);
    }


    render() {
        const gl = this.gl;

        // Clear
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        // Render grid and axes first (behind everything)
        this.renderGrid();
        this.renderAxis();

        if (!this.program || this.gaussianCount === 0) {
            // Just show grid if no Gaussians loaded
            return;
        }

        // Debug: Log first render
        if (!this.hasRendered) {
            this.hasRendered = true;
            console.log(`[Render] Starting render with ${this.gaussianCount.toLocaleString()} Gaussians`);
            console.log(`[Render] View matrix:`, this.camera.viewMatrix.slice(0, 8));
            console.log(`[Render] Projection matrix:`, this.camera.projectionMatrix.slice(0, 8));
        }

        // Use shader program
        gl.useProgram(this.program);

        if (this.writeDepth) {
            // Opaque-ish: nearer splats occlude farther ones
            gl.depthMask(true);
            gl.depthFunc(gl.LESS); // default, safe
        } else {
            // Translucent accumulation: no depth writes, still depth test
            gl.depthMask(false);
            gl.depthFunc(gl.LEQUAL); // keeps frontmost already-written depth; experimentation OK
        }


        // Set uniforms
        gl.uniformMatrix4fv(this.locations.u_viewMatrix, false, this.camera.viewMatrix);
        gl.uniformMatrix4fv(this.locations.u_projectionMatrix, false, this.camera.projectionMatrix);
        gl.uniformMatrix4fv(this.locations.u_objectTransform, false, this.objectTransformMatrix);


        this.bindInstanced();
        this.extInst.drawArraysInstancedANGLE(gl.TRIANGLE_STRIP, 0, 4, this.gaussianCount);

        // Cleanup
        gl.disableVertexAttribArray(this.locations.a_quadPos);
        gl.disableVertexAttribArray(this.locations.a_center);
        gl.disableVertexAttribArray(this.locations.a_quat);
        gl.disableVertexAttribArray(this.locations.a_color);
        gl.disableVertexAttribArray(this.locations.a_opacity);
        gl.disableVertexAttribArray(this.locations.a_scale);
    }

    bindAttribute(buffer, location, size) {
        const gl = this.gl;
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
    }

    updateFPS() {
        this.frameCount++;
        const now = performance.now();
        const elapsed = now - this.lastTime;

        if (elapsed >= 1000) {
            this.fps = Math.round((this.frameCount * 1000) / elapsed);
            document.getElementById('fps').textContent = this.fps;
            this.frameCount = 0;
            this.lastTime = now;
        }
    }

    setupInitialCamera(modelInfo) {
        // Position camera to view entire model
        const center = modelInfo.center;
        const size = modelInfo.size;

        // Camera distance should be about 2x the model size
        const distance = size * 2.0;

        // Position camera looking at model from a good angle
        const cameraPos = [
            center[0] + distance * 0.5,
            center[1] + distance * 0.3,
            center[2] + distance * 0.8
        ];

        // Create view matrix (look at model center from camera position)
        this.camera.viewMatrix = this.createLookAtMatrix(cameraPos, center, [0, 1, 0]);

        console.log(`Camera positioned at distance ${distance.toFixed(1)} from model`);
        console.log(`Looking at center: [${center[0].toFixed(1)}, ${center[1].toFixed(1)}, ${center[2].toFixed(1)}]`);
    }

    createLookAtMatrix(eye, center, up) {
        // Z axis (camera to target, then negate for view space)
        const z = [
            eye[0] - center[0],
            eye[1] - center[1],
            eye[2] - center[2]
        ];
        const zLen = Math.sqrt(z[0]*z[0] + z[1]*z[1] + z[2]*z[2]);
        z[0] /= zLen; z[1] /= zLen; z[2] /= zLen;

        // X axis (cross product of up and z)
        const x = [
            up[1]*z[2] - up[2]*z[1],
            up[2]*z[0] - up[0]*z[2],
            up[0]*z[1] - up[1]*z[0]
        ];
        const xLen = Math.sqrt(x[0]*x[0] + x[1]*x[1] + x[2]*x[2]);
        x[0] /= xLen; x[1] /= xLen; x[2] /= xLen;

        // Y axis (cross product of z and x)
        const y = [
            z[1]*x[2] - z[2]*x[1],
            z[2]*x[0] - z[0]*x[2],
            z[0]*x[1] - z[1]*x[0]
        ];

        // Create view matrix
        return new Float32Array([
            x[0], y[0], z[0], 0,
            x[1], y[1], z[1], 0,
            x[2], y[2], z[2], 0,
            -(x[0]*eye[0] + x[1]*eye[1] + x[2]*eye[2]),
            -(y[0]*eye[0] + y[1]*eye[1] + y[2]*eye[2]),
            -(z[0]*eye[0] + z[1]*eye[1] + z[2]*eye[2]),
            1
        ]);
    }

    // Matrix utilities
    createIdentityMatrix() {
        return new Float32Array([
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1
        ]);
    }

    createPerspectiveMatrix(fovDegrees, aspect, near, far) {
        const fov = fovDegrees * Math.PI / 180;
        const f = 1.0 / Math.tan(fov / 2);
        const nf = 1 / (near - far);

        return new Float32Array([
            f / aspect, 0, 0, 0,
            0, f, 0, 0,
            0, 0, (far + near) * nf, -1,
            0, 0, 2 * far * near * nf, 0
        ]);
    }

    applyObjectTransform(mayaMatrix) {
        /**
         * Apply object transformation from Maya to all Gaussians
         *
         * @param {Array} mayaMatrix - 4x4 transformation matrix from Maya (row-major, 16 floats)
         *
         * Maya matrix format is row-major:
         * [m00, m01, m02, m03,
         *  m10, m11, m12, m13,
         *  m20, m21, m22, m23,
         *  m30, m31, m32, m33]
         *
         * WebGL expects column-major. Maya uses row-vectors (v*M), WebGL uses column-vectors (M*v)
         * To convert: keep matrix as-is (don't transpose) because Maya's row-major with row-vectors
         * equals WebGL's column-major with column-vectors
         */
        if (!mayaMatrix || mayaMatrix.length !== 16) {
            console.error('[ObjectTransform] Invalid matrix received:', mayaMatrix);
            return;
        }

        // Maya's row-major matrix can be used directly in WebGL's column-major layout
        // This preserves the correct rotation direction
        this.objectTransformMatrix = new Float32Array(mayaMatrix);

        // Debug: Log first few transforms
        if (!this.transformUpdateCount) this.transformUpdateCount = 0;
        this.transformUpdateCount++;

        if (this.transformUpdateCount <= 3) {
            console.log(`[ObjectTransform] Update #${this.transformUpdateCount}:`, {
                translation: [mayaMatrix[12], mayaMatrix[13], mayaMatrix[14]],
                rotation: 'applied',
                matrix: this.objectTransformMatrix
            });
        }
    }
}
