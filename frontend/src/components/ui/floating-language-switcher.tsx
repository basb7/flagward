'use client';

import { LanguageSwitcher } from '@/components/ui/language-switcher';
import { changeLocaleAction } from '@/i18n/actions';

/**
 * The switcher's fixed corner is chrome, not page content, so it is defined
 * here once instead of at every public-route call site: a page's early
 * return can skip content it renders inline, but it can never skip
 * something its layout renders alongside it. One definition also means
 * moving the corner is one edit, not five.
 */
export function FloatingLanguageSwitcher() {
  return (
    <div className="fixed top-4 right-4">
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />
    </div>
  );
}
