import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import clsx from 'clsx';
import type { ReactNode } from 'react';

interface TooltipProps {
  children: ReactNode;
  content: ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  className?: string;
  sideOffset?: number;
  delayDuration?: number;
  maxWidth?: string;
}

export function Tooltip({
  children,
  content,
  side = 'top',
  align = 'center',
  className,
  sideOffset = 6,
  delayDuration = 300,
  maxWidth = 'max-w-xs',
}: TooltipProps) {
  if (!content) return <>{children}</>;
  return (
    <TooltipPrimitive.Root delayDuration={delayDuration}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          align={align}
          sideOffset={sideOffset}
          collisionPadding={10}
          avoidCollisions
          className={clsx(
            'z-[9999] overflow-hidden rounded-md',
            'border border-border bg-bg-tertiary shadow-lg',
            'px-3 py-2 text-xs text-text-primary whitespace-pre-line',
            maxWidth,
            'break-words animate-fade-in',
            className,
          )}
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-bg-tertiary" width={10} height={5} />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
