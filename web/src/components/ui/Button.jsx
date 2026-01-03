import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function Button({
    children,
    variant = 'primary',
    size = 'md',
    className,
    ...props
}) {
    const baseStyles = 'inline-flex items-center justify-center rounded transition-colors duration-200 font-medium font-heading focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:pointer-events-none cursor-pointer';

    const variants = {
        primary: 'bg-primary hover:bg-primary/90 text-primary-foreground focus:ring-primary',
        secondary: 'bg-slate-700 hover:bg-slate-600 text-slate-50 focus:ring-slate-500',
        outline: 'border border-slate-700 hover:bg-slate-800 text-slate-300 focus:ring-slate-500',
        ghost: 'hover:bg-slate-800 text-slate-300 hover:text-white',
        danger: 'bg-danger hover:bg-danger/90 text-white focus:ring-danger',
    };

    const sizes = {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4 py-2 text-sm',
        lg: 'h-12 px-6 text-base',
        icon: 'h-10 w-10 p-2',
    };

    return (
        <button
            className={twMerge(baseStyles, variants[variant], sizes[size], className)}
            {...props}
        >
            {children}
        </button>
    );
}
