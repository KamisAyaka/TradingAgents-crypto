import { twMerge } from 'tailwind-merge';

export function Card({ children, className, variant = 'default' }) {
    const variants = {
        default: 'bg-surface/60 backdrop-blur-md border border-slate-700/60 shadow-xl',
        terminal: 'bg-[#0c0c0c] border border-slate-800 shadow-inner font-mono',
        highlight: 'bg-surface/80 border border-primary/30 shadow-primary/5',
    };

    return (
        <div
            className={twMerge(
                'rounded-lg overflow-hidden transition-all duration-300',
                variants[variant] || variants.default,
                className
            )}
        >
            {/* Optional Top accent line for "Agent" feel */}
            {variant === 'default' && (
                <div className="h-0.5 w-full bg-gradient-to-r from-transparent via-slate-600 to-transparent opacity-30" />
            )}
            {children}
        </div>
    );
}
