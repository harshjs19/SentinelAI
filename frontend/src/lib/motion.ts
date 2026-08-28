import type { Transition, Variants } from "framer-motion";

export const motionDuration = {
  fast: 0.16,
  standard: 0.26,
  enter: 0.38,
  cinematic: 0.68,
  lineage: 1.65,
} as const;

export const premiumEase = [0.22, 1, 0.36, 1] as const;

export const premiumTransition: Transition = {
  duration: motionDuration.standard,
  ease: premiumEase,
};

export const pageTransition: Transition = {
  duration: motionDuration.enter,
  ease: premiumEase,
};

export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 10, filter: "blur(4px)" },
  visible: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -5, filter: "blur(2px)" },
};

export const revealTransition = (index = 0): Transition => ({
  duration: motionDuration.enter,
  delay: Math.min(index * 0.07, 0.28),
  ease: premiumEase,
});
