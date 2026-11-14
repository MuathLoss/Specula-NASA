import type { Metadata } from "next";
import { SpeculaApp } from "@/components/SpeculaApp";

export const metadata: Metadata = { title: "Cosmos" };

export default function CosmosPage() {
  return <SpeculaApp variant="cosmos" />;
}
