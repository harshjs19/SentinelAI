import { Float, Line } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, type MutableRefObject, type PointerEvent as ReactPointerEvent } from "react";
import type { Group, Mesh, MeshStandardMaterial, Points } from "three";

const nodes = [
  [-2.35, 0.65, -0.2],
  [2.25, 0.72, -0.35],
  [-1.75, -1.35, 0.15],
  [1.85, -1.2, 0.05],
] as const;

interface PointerTarget {
  x: number;
  y: number;
}

function ParticleField({ motionEnabled, compact }: { motionEnabled: boolean; compact: boolean }) {
  const particles = useRef<Points>(null);
  const positions = useMemo(() => {
    const count = compact ? 46 : 84;
    const values = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const angle = index * 2.39996;
      const radius = 1.75 + ((index * 37) % 100) / 78;
      values[index * 3] = Math.cos(angle) * radius;
      values[index * 3 + 1] = Math.sin(angle * 1.31) * (1.1 + (index % 5) * 0.12);
      values[index * 3 + 2] = Math.sin(angle) * radius * 0.45 - 0.65;
    }
    return values;
  }, [compact]);

  useFrame((_, delta) => {
    if (motionEnabled && particles.current) particles.current.rotation.y += delta * 0.018;
  });

  return (
    <points ref={particles}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial color="#8bdff0" size={compact ? 0.018 : 0.022} transparent opacity={0.28} depthWrite={false} sizeAttenuation />
    </points>
  );
}

function Core({ motionEnabled, compact, pointerTarget }: { motionEnabled: boolean; compact: boolean; pointerTarget: MutableRefObject<PointerTarget> }) {
  const group = useRef<Group>(null);
  const orbit = useRef<Group>(null);
  const nucleus = useRef<MeshStandardMaterial>(null);
  const pulses = useRef<Array<Mesh | null>>([]);
  useFrame((state, delta) => {
    if (!motionEnabled || !group.current || !orbit.current) return;
    const elapsed = state.clock.elapsedTime;
    const scrollProgress = Math.min(window.scrollY / 760, 1);
    group.current.rotation.y += delta * 0.08;
    group.current.rotation.x += (pointerTarget.current.y * 0.075 - group.current.rotation.x) * 0.035;
    group.current.rotation.z += (-pointerTarget.current.x * 0.035 - group.current.rotation.z) * 0.035;
    group.current.scale.setScalar(1 - scrollProgress * 0.045);
    orbit.current.rotation.z += delta * 0.035;
    state.camera.position.x += (pointerTarget.current.x * 0.2 - state.camera.position.x) * 0.035;
    state.camera.position.y += (0.12 + pointerTarget.current.y * 0.13 - state.camera.position.y) * 0.035;
    state.camera.position.z += (6.65 + scrollProgress * 0.22 - state.camera.position.z) * 0.035;
    state.camera.lookAt(0, 0, 0);
    if (nucleus.current) nucleus.current.emissiveIntensity = 1.05 + Math.sin(elapsed * 1.15) * 0.14;
    pulses.current.forEach((pulse, index) => {
      if (!pulse) return;
      const progress = (elapsed * 0.105 + index * 0.23) % 1;
      const destination = nodes[index];
      if (!destination) return;
      pulse.position.set(destination[0] * progress, destination[1] * progress, destination[2] * progress);
      const visibility = Math.sin(progress * Math.PI);
      pulse.scale.setScalar(0.65 + visibility * 0.55);
    });
  });

  return (
    <group ref={group}>
      <ParticleField motionEnabled={motionEnabled} compact={compact} />
      <Float speed={motionEnabled ? 0.42 : 0} rotationIntensity={motionEnabled ? 0.1 : 0} floatIntensity={motionEnabled ? 0.14 : 0}>
        <mesh scale={1.08}>
          <icosahedronGeometry args={[1.05, 3]} />
          <meshPhysicalMaterial color="#3cb8d4" emissive="#075a70" emissiveIntensity={0.34} transparent opacity={0.18} roughness={0.16} metalness={0.42} transmission={0.5} depthWrite={false} />
        </mesh>
        <mesh scale={0.98}>
          <icosahedronGeometry args={[1.05, 2]} />
          <meshBasicMaterial color="#77dbef" transparent opacity={0.3} wireframe depthWrite={false} />
        </mesh>
        <mesh scale={0.56}>
          <icosahedronGeometry args={[1, 4]} />
          <meshStandardMaterial ref={nucleus} color="#b5f3ff" emissive="#168da7" emissiveIntensity={1.05} roughness={0.2} metalness={0.46} />
        </mesh>
        <mesh scale={0.28}>
          <sphereGeometry args={[1, 32, 32]} />
          <meshBasicMaterial color="#e0fbff" transparent opacity={0.78} />
        </mesh>
      </Float>
      <group ref={orbit}>
        <mesh rotation={[Math.PI / 2.45, 0.2, 0]}><torusGeometry args={[1.72, 0.009, 8, 128]} /><meshBasicMaterial color="#70def3" transparent opacity={0.46} /></mesh>
        <mesh rotation={[Math.PI / 1.8, 0.5, 0]}><torusGeometry args={[2.14, 0.006, 8, 128]} /><meshBasicMaterial color="#6d82ae" transparent opacity={0.3} /></mesh>
        <mesh rotation={[Math.PI / 1.32, -0.34, 0.38]}><torusGeometry args={[2.52, 0.004, 8, 160]} /><meshBasicMaterial color="#8ce8f7" transparent opacity={0.16} /></mesh>
      </group>
      <mesh scale={1.42} rotation={[0.22, 0.35, 0]}>
        <icosahedronGeometry args={[1.05, 1]} />
        <meshBasicMaterial color="#8ce7f5" transparent opacity={0.055} wireframe depthWrite={false} />
      </mesh>
      <mesh scale={1.86} rotation={[0.3, -0.18, 0.12]}>
        <icosahedronGeometry args={[1.05, 1]} />
        <meshBasicMaterial color="#6178ae" transparent opacity={0.035} wireframe depthWrite={false} />
      </mesh>
      {nodes.map((position, index) => (
        <group key={index} position={position}>
          <mesh><sphereGeometry args={[0.13, 20, 20]} /><meshStandardMaterial color={index === 3 ? "#e9ba7a" : "#9aeaf8"} emissive={index === 3 ? "#8d531d" : "#167f96"} emissiveIntensity={0.9} /></mesh>
          <mesh scale={2.25}><sphereGeometry args={[0.13, 16, 16]} /><meshBasicMaterial color={index === 3 ? "#e7a65c" : "#5dd7ef"} transparent opacity={0.08} depthWrite={false} /></mesh>
        </group>
      ))}
      {nodes.map((position, index) => (
        <group key={`connection-${index}`}>
          <Line points={[[0, 0, 0], [...position]]} color={index === 3 ? "#cf9c61" : "#4ba9bd"} transparent opacity={0.18} lineWidth={0.55} />
          <mesh ref={(element) => { pulses.current[index] = element; }} position={[position[0] * 0.5, position[1] * 0.5, position[2] * 0.5]}>
            <sphereGeometry args={[0.032, 10, 10]} />
            <meshBasicMaterial color={index === 3 ? "#f0c07e" : "#c1f4ff"} transparent opacity={0.82} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export default function SentinelCoreScene({ motionEnabled, compact }: { motionEnabled: boolean; compact: boolean }) {
  const pointerTarget = useRef<PointerTarget>({ x: 0, y: 0 });
  const trackPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!motionEnabled) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    pointerTarget.current.x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    pointerTarget.current.y = -((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
  };
  const resetPointer = () => { pointerTarget.current = { x: 0, y: 0 }; };

  return (
    <div className="sentinel-core-canvas" onPointerMove={trackPointer} onPointerLeave={resetPointer}>
      <Canvas frameloop={motionEnabled ? "always" : "demand"} camera={{ position: [0, 0.12, 6.65], fov: 41 }} dpr={compact ? 1 : [1, 1.5]} gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}>
        <ambientLight intensity={0.42} />
        <pointLight position={[3, 3, 4]} intensity={19} color="#7be8ff" />
        <pointLight position={[-3, -2, 3]} intensity={11} color="#4a57c8" />
        <pointLight position={[0, 0, 1]} intensity={7} color="#d7f9ff" distance={4} />
        <Core motionEnabled={motionEnabled} compact={compact} pointerTarget={pointerTarget} />
      </Canvas>
    </div>
  );
}
