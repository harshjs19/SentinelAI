import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { motionDuration, premiumEase } from "../lib/motion";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <header className="page-header">
      <motion.div
        initial={reduced ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : motionDuration.enter, ease: premiumEase }}
      >
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </motion.div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
}
