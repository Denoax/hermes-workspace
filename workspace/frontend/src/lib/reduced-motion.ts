import { createContext, useContext } from "react";
import { useReducedMotion as useSystemReducedMotion } from "motion/react";
export const ReducedMotionContext = createContext(false);
export function useReducedMotion() {
  const forced = useContext(ReducedMotionContext);
  const system = useSystemReducedMotion();
  return forced || !!system;
}
