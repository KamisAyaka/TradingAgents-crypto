import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function Badge({ children, variant = 'default', className }) {
    const variants = {
        default: 'bg-slate-700 text-slate-200',
        primary: 'bg-primary/20 text-primary',
        success: 'bg-success/20 text-success',
        danger: 'bg-danger/20 text-danger',
        warning: 'bg-accent/20 text-accent',
        outline: 'border border-slate-700 text-slate-400 bg-transparent',
    };

    return (
        <span
            className={twMerge(
                'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium font-heading tracking-wide',
                variants[variant],
                className
            )}
        >
            {children}
        </span>
    );
}
