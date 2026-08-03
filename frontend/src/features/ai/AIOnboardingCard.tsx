import { Bot, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useReaderStore } from "../../store/readerStore";
import { AIWalkthrough } from "./AIWalkthrough";
import { geminiProvider, openOfficialAILink } from "./providerMetadata";

export function AIOnboardingCard({ configured }: { configured: boolean }) {
  const dismissed = useReaderStore((state) => state.aiExperience.onboardingDismissed);
  const dismiss = useReaderStore((state) => state.setAIExperience);
  const [guideOpen, setGuideOpen] = useState(false);
  if (configured || dismissed) return null;
  return <>
    <section className="ai-onboarding-card" aria-labelledby="ai-onboarding-title">
      <div className="ai-onboarding-icon"><Bot/></div><div>
        <p className="eyebrow">Optional extension</p><h2 id="ai-onboarding-title">Enable Optional AI Features</h2>
        <p>BookBuddy works completely offline. A Gemini key can add explanations, translation, chapter analysis, AI dictionary help, and optional image understanding.</p>
        <div className="ai-onboarding-actions">
          <button className="primary" onClick={() => void openOfficialAILink(geminiProvider.links.studio)}><ExternalLink/>Get Free API Key</button>
          <button className="secondary" onClick={() => setGuideOpen(true)}>How to Get One</button>
          <Link className="secondary" to="/settings?section=ai">Configure</Link>
          <button className="text-button" onClick={() => dismiss({ onboardingDismissed: true })}>Skip for now</button>
        </div>
      </div>
    </section>
    <AIWalkthrough open={guideOpen} onOpenChange={setGuideOpen}/>
  </>;
}
