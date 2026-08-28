import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

import { motionDuration, premiumEase } from "../lib/motion";

export function MetricCard({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  note: string;
  icon: LucideIcon;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.article
      className="metric-card glass-card interactive-card"
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0 : motionDuration.enter, ease: premiumEase }}
    >
      <div className="metric-card__icon">
        <Icon aria-hidden="true" />
      </div>
      <div>
        <span>{label}</span>
        <motion.strong
          initial={reduced ? false : { opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduced ? 0 : motionDuration.enter, delay: reduced ? 0 : 0.08, ease: premiumEase }}
        >
          {value}
        </motion.strong>
        <small>{note}</small>
      </div>
    </motion.article>
  );
}
