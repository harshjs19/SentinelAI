import { Float } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";

const nodes = [
  [-2.35, 0.65, -0.2],
  [2.25, 0.72, -0.35],
  [-1.75, -1.35, 0.15],
  [1.85, -1.2, 0.05],
] as const;

function Core({ motionEnabled }: { motionEnabled: boolean }) {
  const group = useRef<Group>(null);
  useFrame((state, delta) => {
    if (!motionEnabled || !group.current) return;
    group.current.rotation.y += delta * 0.08;
    group.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.18) * 0.06;
  });

  return (
    <group ref={group}>
      <Float speed={motionEnabled ? 0.55 : 0} rotationIntensity={motionEnabled ? 0.14 : 0} floatIntensity={motionEnabled ? 0.18 : 0}>
        <mesh>
          <icosahedronGeometry args={[1.05, 2]} />
          <meshPhysicalMaterial color="#45c9e7" emissive="#0f7f9d" emissiveIntensity={0.45} transparent opacity={0.42} roughness={0.18} metalness={0.35} transmission={0.28} wireframe />
        </mesh>
        <mesh scale={0.62}>
          <icosahedronGeometry args={[1, 3]} />
          <meshStandardMaterial color="#98edff" emissive="#1689a4" emissiveIntensity={0.8} roughness={0.25} metalness={0.5} />
        </mesh>
      </Float>
      <mesh rotation={[Math.PI / 2.45, 0.2, 0]}><torusGeometry args={[1.75, 0.008, 8, 120]} /><meshBasicMaterial color="#5cd8f2" transparent opacity={0.42} /></mesh>
      <mesh rotation={[Math.PI / 1.8, 0.5, 0]}><torusGeometry args={[2.18, 0.006, 8, 120]} /><meshBasicMaterial color="#617fa8" transparent opacity={0.28} /></mesh>
      {nodes.map((position, index) => (
        <group key={index} position={position}>
          <mesh><sphereGeometry args={[0.14, 24, 24]} /><meshStandardMaterial color={index === 3 ? "#eeb66b" : "#8be8fa"} emissive={index === 3 ? "#9a5a1d" : "#167f96"} emissiveIntensity={0.8} /></mesh>
          <mesh scale={2.1}><sphereGeometry args={[0.14, 18, 18]} /><meshBasicMaterial color="#5dd7ef" transparent opacity={0.08} /></mesh>
        </group>
      ))}
    </group>
  );
}

export default function SentinelCoreScene({ motionEnabled }: { motionEnabled: boolean }) {
  return (
    <Canvas camera={{ position: [0, 0.15, 6.6], fov: 42 }} dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}>
      <ambientLight intensity={0.35} />
      <pointLight position={[3, 3, 4]} intensity={18} color="#7be8ff" />
      <pointLight position={[-3, -2, 3]} intensity={10} color="#4a57c8" />
      <Core motionEnabled={motionEnabled} />
    </Canvas>
  );
}
