import { AuthErrorNotice } from "@/components/landing/AuthErrorNotice";
import { CallToAction } from "@/components/landing/CallToAction";
import { Hero } from "@/components/landing/Hero";
import { HowItWorksSection } from "@/components/landing/HowItWorksSection";
import { ProblemSection } from "@/components/landing/ProblemSection";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { SiteHeader } from "@/components/landing/SiteHeader";

type HomePageProps = {
  searchParams: Promise<{ auth_error?: string | string[] }>;
};

/** Public landing page for psychologists. */
export default async function HomePage({ searchParams }: HomePageProps) {
  const { auth_error: authError } = await searchParams;

  return (
    <>
      <SiteHeader />
      {typeof authError === "string" && <AuthErrorNotice error={authError} />}
      <main>
        <Hero />
        <ProblemSection />
        <HowItWorksSection />
        <CallToAction />
      </main>
      <SiteFooter />
    </>
  );
}
