import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { pageTransition, pageVariants } from "../lib/motion";

export function PageTransition({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className="page-transition"
      initial={reduced ? false : "hidden"}
      animate="visible"
      exit={reduced ? undefined : "exit"}
      variants={pageVariants}
      transition={reduced ? { duration: 0 } : pageTransition}
    >
      {children}
    </motion.div>
  );
}
