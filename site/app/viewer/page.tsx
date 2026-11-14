import type { Metadata } from "next";
import { SpeculaApp } from "@/components/SpeculaApp";

export const metadata: Metadata = { title: "Sky" };

export default function ViewerPage() {
  return <SpeculaApp variant="viewer" />;
}
