import { FloatingLanguageSwitcher } from '@/components/ui/floating-language-switcher';

export default function RegisterLayout({
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
