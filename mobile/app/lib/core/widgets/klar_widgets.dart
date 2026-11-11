import 'package:flutter/material.dart';

import '../design/app_theme.dart';

/// A small label above one large amount: the opening element of a page.
class AmountHeadline extends StatelessWidget {
  const AmountHeadline({
    required this.label,
    required this.amount,
    this.note,
    this.size = 44,
    super.key,
  });

  final String label;
  final String amount;
  final String? note;
  final double size;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: textTheme.bodyMedium),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(
            amount,
            style: TextStyle(
              color: AppTheme.ink,
              fontSize: size,
              height: 1.1,
              fontWeight: FontWeight.w700,
              letterSpacing: -1.6,
            ),
          ),
        ),
        if (note != null) ...[
          const SizedBox(height: 4),
          Text(note!, style: textTheme.bodyMedium),
        ],
      ],
    );
  }
}

/// A thick rounded progress bar. Turns orange when [over] is set.
class ThickBar extends StatelessWidget {
  const ThickBar({
    required this.value,
    this.over = false,
    this.height = 10,
    super.key,
  });

  final double value;
  final bool over;
  final double height;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(height / 2),
      child: LinearProgressIndicator(
        value: over ? 1 : value,
        minHeight: height,
        backgroundColor: AppTheme.softBrand,
        valueColor: AlwaysStoppedAnimation(
          over ? AppTheme.warn : AppTheme.brand,
        ),
      ),
    );
  }
}

/// A section title with an optional text action on the right.
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.title, {this.action, this.onAction, super.key});

  final String title;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(title, style: Theme.of(context).textTheme.titleLarge),
        ),
        if (action != null)
          TextButton(
            onPressed: onAction,
            style: TextButton.styleFrom(
              foregroundColor: AppTheme.brand,
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.only(left: 8),
            ),
            child: Text(action!),
          ),
      ],
    );
  }
}

/// A white panel drawn with an ink outline instead of a tinted fill.
class OutlinedPanel extends StatelessWidget {
  const OutlinedPanel({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.ink, width: 1.5),
      ),
      child: child,
    );
  }
}

/// One line of a money list: initial, name, detail and amount.
class EntryRow extends StatelessWidget {
  const EntryRow({
    required this.title,
    required this.detail,
    required this.amount,
    this.positive = false,
    this.badge,
    this.onTap,
    super.key,
  });

  final String title;
  final String detail;
  final String amount;
  final bool positive;
  final String? badge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final initial = title.trim().isEmpty
        ? '?'
        : title.trim().substring(0, 1).toUpperCase();
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 60),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Row(
            children: [
              Container(
                width: 38,
                height: 38,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: positive ? AppTheme.brand : AppTheme.softBrand,
                  shape: BoxShape.circle,
                ),
                child: Text(
                  initial,
                  style: TextStyle(
                    color: positive ? Colors.white : AppTheme.brand,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      detail,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodySmall,
                    ),
                    if (badge != null) ...[
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 1,
                        ),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: AppTheme.brand),
                        ),
                        child: Text(
                          badge!,
                          style: const TextStyle(
                            color: AppTheme.brand,
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Text(
                amount,
                style: textTheme.titleMedium?.copyWith(
                  color: positive ? AppTheme.brand : AppTheme.ink,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A short message for empty lists and missing data.
class QuietMessage extends StatelessWidget {
  const QuietMessage(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}

String formatShortDate(String value) {
  final date = DateTime.tryParse(value);
  if (date == null) return value;
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  return '$day.$month.${date.year}';
}
