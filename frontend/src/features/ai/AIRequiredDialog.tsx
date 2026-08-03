import * as Dialog from "@radix-ui/react-dialog";
import { Bot, X } from "lucide-react";
import { useState } from "react";
import { AIWalkthrough } from "./AIWalkthrough";

export function AIRequiredDialog({ open, feature, onOpenChange }: { open: boolean; feature: string; onOpenChange: (open: boolean) => void }) {
  const [guideOpen, setGuideOpen] = useState(false);
  return <><Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="book-dialog ai-required-dialog">
    <Dialog.Close className="dialog-x" aria-label="Close"><X/></Dialog.Close><Dialog.Title><Bot/>Optional AI key required</Dialog.Title>
    <Dialog.Description>{feature} requires an optional Gemini API key. Reading and local features remain available without one.</Dialog.Description>
    <div className="dialog-actions"><button className="primary" onClick={() => { onOpenChange(false); window.location.hash = "#/settings?section=ai"; }}>Configure</button><button className="secondary" onClick={() => setGuideOpen(true)}>Learn More</button><Dialog.Close className="text-button">Cancel</Dialog.Close></div>
  </Dialog.Content></Dialog.Portal></Dialog.Root><AIWalkthrough open={guideOpen} onOpenChange={setGuideOpen}/></>;
}
