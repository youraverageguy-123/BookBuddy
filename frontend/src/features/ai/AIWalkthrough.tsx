import * as Dialog from "@radix-ui/react-dialog";
import { ExternalLink, X } from "lucide-react";
import { geminiProvider, openOfficialAILink } from "./providerMetadata";

export function AIWalkthrough({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal>
    <Dialog.Overlay className="dialog-overlay"/>
    <Dialog.Content className="book-dialog ai-walkthrough" aria-describedby="ai-walkthrough-description">
      <Dialog.Close className="dialog-x" aria-label="Close AI setup guide"><X/></Dialog.Close>
      <Dialog.Title>How to enable optional AI</Dialog.Title>
      <Dialog.Description id="ai-walkthrough-description">BookBuddy remains a complete offline reader if you stop at any point.</Dialog.Description>
      <ol>{geminiProvider.setupSteps.map((step) => <li key={step}>{step}</li>)}</ol>
      <div className="official-links">
        <OfficialAILink label="Get a free API key" url={geminiProvider.links.studio}/>
        <OfficialAILink label="Official API key guide" url={geminiProvider.links.keyGuide}/>
        <OfficialAILink label="Gemini documentation" url={geminiProvider.links.documentation}/>
      </div>
      <Dialog.Close className="secondary">Done</Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}

export function OfficialAILink({ label, url }: { label: string; url: string }) {
  return <a
    className="official-link"
    href={url}
    target="_blank"
    rel="noreferrer"
    onClick={(event) => {
      event.preventDefault();
      void openOfficialAILink(url);
    }}
  >
    <span><ExternalLink aria-hidden="true"/>{label}</span>
    <code>{url}</code>
  </a>;
}
