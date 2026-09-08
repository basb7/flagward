'use client';

import { Languages } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { useTransition } from 'react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LOCALE_LABELS, LOCALES, type Locale } from '@/i18n/locales';
import { useToast } from '@/lib/toast-context';

/**
 * Mounted once on every layout that needs it -- the dashboard nav today,
 * the public routes in slices 2 and 3 -- rather than duplicated, so a
 * change to how a locale is chosen only has one place to happen.
 */
export function LanguageSwitcher({
  changeLocaleAction,
}: {
  changeLocaleAction: (locale: Locale) => Promise<void>;
}) {
  const locale = useLocale();
  const t = useTranslations('languageSwitcher');
  const [isPending, startTransition] = useTransition();
  const { error: showError } = useToast();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('label')}
            disabled={isPending}
            className="gap-1.5 text-muted-foreground hover:text-foreground"
          />
        }
      >
        <Languages className="size-4" />
        <span className="sr-only sm:not-sr-only">
          {LOCALE_LABELS[locale as Locale]}
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup
          value={locale}
          onValueChange={(value) => {
            // An async transition function is how React 19 keeps `isPending`
            // true until this settles. `void`-ing the call instead (as this
            // used to) discarded the rejection outright. The selection
            // itself was never the problem -- it is controlled by the
            // server-rendered locale and stays put on failure, which
            // `leaves the selection on the real locale when the action
            // rejects` pins -- but nobody was told the switch had not taken.
            startTransition(async () => {
              try {
                await changeLocaleAction(value as Locale);
              } catch {
                showError(t('error'));
              }
            });
          }}
        >
          {LOCALES.map((code) => (
            <DropdownMenuRadioItem key={code} value={code}>
              {LOCALE_LABELS[code]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
