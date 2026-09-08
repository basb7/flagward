import { FloatingLanguageSwitcher } from '@/components/ui/floating-language-switcher';

export default function ResetPasswordLayout({
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
