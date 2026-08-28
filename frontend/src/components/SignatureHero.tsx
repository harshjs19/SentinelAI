import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { usePointerSpotlight } from "../hooks/usePointerSpotlight";
import { motionDuration, premiumEase } from "../lib/motion";
import { PageScene, type PageSceneItem, type PageSceneVariant } from "./PageScene";

export function SignatureHero({
  index,
  eyebrow,
  title,
  description,
  variant,
  sceneKicker,
  sceneTitle,
  sceneNote,
  sceneItems,
  facts,
  actions,
  sceneFooter,
}: {
  index: string;
  eyebrow: string;
  title: ReactNode;
  description: string;
  variant: PageSceneVariant;
  sceneKicker: string;
  sceneTitle: string;
  sceneNote: string;
  sceneItems?: PageSceneItem[];
  facts?: ReactNode;
  actions?: ReactNode;
  sceneFooter?: ReactNode;
}) {
  const reduced = useReducedMotion();
  const spotlight = usePointerSpotlight<HTMLElement>();

  return (
    <header
      ref={spotlight.ref}
      onPointerMove={spotlight.onPointerMove}
      data-index={index}
      className={`signature-hero signature-hero--${variant} glass-panel spotlight-surface`}
    >
      <motion.div
        className="signature-hero__copy"
        initial={reduced ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduced ? 0 : motionDuration.enter, ease: premiumEase }}
      >
        <div className="signature-hero__chapter">
          <p className="eyebrow">{eyebrow}</p>
          <span>{index}</span>
        </div>
        <h1>{title}</h1>
        <p className="signature-hero__description">{description}</p>
        {facts && <div className="signature-hero__facts">{facts}</div>}
        {actions && <div className="signature-hero__actions">{actions}</div>}
      </motion.div>

      <motion.div
        className="signature-hero__visual"
        initial={reduced ? false : { opacity: 0, x: 14, filter: "blur(5px)" }}
        animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
        transition={{ duration: reduced ? 0 : motionDuration.cinematic, ease: premiumEase }}
      >
        <PageScene
          variant={variant}
          kicker={sceneKicker}
          title={sceneTitle}
          note={sceneNote}
          items={sceneItems}
          footer={sceneFooter}
        />
      </motion.div>
    </header>
  );
}
