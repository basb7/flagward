import { FloatingLanguageSwitcher } from '@/components/ui/floating-language-switcher';

export default function ForgotPasswordLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {children}
      <FloatingLanguageSwitcher />
    </>
  );
}
