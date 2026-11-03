import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/data/account.dart';
import '../../core/data/account_controller.dart';
import '../../core/data/demo_finance_data.dart';

class AccountsPage extends StatefulWidget {
  const AccountsPage({super.key, required this.controller});

  final AccountController controller;

  @override
  State<AccountsPage> createState() => _AccountsPageState();
}

class _AccountsPageState extends State<AccountsPage> {
  Future<void> _addAccount() async {
    final account = await _editAccountDialog();
    if (account != null) await _saveAccount(account);
  }

  Future<void> _editAccount(Account current) async {
    final account = await _editAccountDialog(current: current);
    if (account != null) await _saveAccount(account);
  }

  Future<void> _saveAccount(Account account) async {
    final saved = await widget.controller.save(account);
    if (!saved && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Konto konnte nicht gespeichert werden.')),
      );
    }
  }

  Future<void> _deleteAccount(Account account) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Konto löschen?'),
        content: Text('„${account.name}“ wird von diesem Gerät entfernt.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Löschen'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    final deleted = await widget.controller.delete(account.id);
    if (!deleted && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Konto konnte nicht gelöscht werden.')),
      );
    }
  }

  Future<Account?> _editAccountDialog({Account? current}) async {
    final formKey = GlobalKey<FormState>();
    final nameController = TextEditingController(text: current?.name ?? '');
    final institutionController = TextEditingController(
      text: current?.institution ?? '',
    );
    final suffixController = TextEditingController(
      text: current?.accountSuffix ?? '',
    );
    final balanceController = TextEditingController(
      text: current == null
          ? ''
          : (current.balanceCents / 100)
                .toStringAsFixed(2)
                .replaceAll('.', ','),
    );
    var selectedType = current?.type ?? AccountType.checking;

    final result = await showDialog<Account>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(
            current == null ? 'Konto hinzufügen' : 'Konto bearbeiten',
          ),
          content: Form(
            key: formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: nameController,
                    autofocus: true,
                    maxLength: 60,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                      labelText: 'Kontoname',
                      hintText: 'z. B. Girokonto',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) => (value ?? '').trim().isEmpty
                        ? 'Bitte einen Kontonamen eingeben.'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<AccountType>(
                    initialValue: selectedType,
                    decoration: const InputDecoration(
                      labelText: 'Kontotyp',
                      border: OutlineInputBorder(),
                    ),
                    items: AccountType.values
                        .map(
                          (type) => DropdownMenuItem(
                            value: type,
                            child: Text(type.label),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value != null) {
                        setDialogState(() => selectedType = value);
                      }
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: institutionController,
                    maxLength: 60,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                      labelText: 'Bank / Anbieter (optional)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: suffixController,
                    maxLength: 4,
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(4),
                    ],
                    decoration: const InputDecoration(
                      labelText: 'Letzte 4 Ziffern (optional)',
                      helperText: 'Keine vollständige IBAN oder Kartennummer',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) {
                      final suffix = value ?? '';
                      if (suffix.isNotEmpty && suffix.length != 4) {
                        return 'Bitte genau 4 Ziffern eingeben.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: balanceController,
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                      signed: true,
                    ),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(RegExp(r'[0-9,.-]')),
                    ],
                    decoration: const InputDecoration(
                      labelText: 'Aktueller Kontostand',
                      suffixText: '€',
                      helperText: 'Negativer Betrag z. B. bei Kreditkarten',
                      border: OutlineInputBorder(),
                    ),
                    validator: (value) {
                      final amount = double.tryParse(
                        (value ?? '').trim().replaceAll(',', '.'),
                      );
                      if (amount == null || !amount.isFinite) {
                        return 'Bitte einen gültigen Betrag eingeben.';
                      }
                      if (amount.abs() > 999999999) {
                        return 'Der Betrag ist zu groß.';
                      }
                      return null;
                    },
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Abbrechen'),
            ),
            FilledButton(
              onPressed: () {
                if (!formKey.currentState!.validate()) return;
                final balance = double.parse(
                  balanceController.text.trim().replaceAll(',', '.'),
                );
                Navigator.pop(
                  dialogContext,
                  Account(
                    id: current?.id ?? Account.createId(),
                    name: nameController.text.trim(),
                    institution: institutionController.text.trim(),
                    accountSuffix: suffixController.text.trim(),
                    type: selectedType,
                    balanceCents: (balance * 100).round(),
                  ),
                );
              },
              child: const Text('Speichern'),
            ),
          ],
        ),
      ),
    );

    nameController.dispose();
    institutionController.dispose();
    suffixController.dispose();
    balanceController.dispose();
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, child) {
        if (widget.controller.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (widget.controller.loadError != null) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline_rounded, size: 34),
                  const SizedBox(height: 10),
                  const Text(
                    'Deine Konten konnten nicht geladen werden.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.tonalIcon(
                    onPressed: widget.controller.load,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Erneut laden'),
                  ),
                ],
              ),
            ),
          );
        }
        return _buildAccounts(context);
      },
    );
  }

  Widget _buildAccounts(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final accounts = widget.controller.accounts;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Deine Konten',
                    style: textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    'Manuell gepflegte Kontostände – keine Bankverbindung.',
                    style: TextStyle(color: colors.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.tonalIcon(
              onPressed: widget.controller.isSaving ? null : _addAccount,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: const Text('Konto'),
            ),
          ],
        ),
        const SizedBox(height: 16),
        _AccountSummaryCard(
          count: accounts.length,
          totalBalanceCents: widget.controller.totalBalanceCents,
        ),
        const SizedBox(height: 20),
        Text(
          'KONTEN AUF DIESEM GERÄT',
          style: textTheme.labelSmall?.copyWith(
            color: colors.onSurfaceVariant,
            fontWeight: FontWeight.w800,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: 9),
        if (accounts.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: colors.outlineVariant),
            ),
            child: Column(
              children: [
                Icon(
                  Icons.account_balance_wallet_outlined,
                  color: colors.onSurfaceVariant,
                  size: 34,
                ),
                const SizedBox(height: 10),
                const Text(
                  'Noch keine Konten angelegt',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 5),
                Text(
                  'Lege ein Konto an und trage den Stand selbst ein. '
                  'Es werden keine Bankdaten abgerufen.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: colors.onSurfaceVariant,
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 13),
                FilledButton.icon(
                  onPressed: widget.controller.isSaving ? null : _addAccount,
                  icon: const Icon(Icons.add_rounded),
                  label: const Text('Erstes Konto anlegen'),
                ),
              ],
            ),
          )
        else
          ...accounts.map(
            (account) => _AccountCard(
              account: account,
              enabled: !widget.controller.isSaving,
              onEdit: () => _editAccount(account),
              onDelete: () => _deleteAccount(account),
            ),
          ),
        const SizedBox(height: 12),
        Text(
          'Die Kontostände werden verschlüsselt auf diesem Gerät gespeichert. '
          'Sie sind manuelle Angaben und werden nicht mit einer Bank abgeglichen.',
          textAlign: TextAlign.center,
          style: textTheme.labelSmall?.copyWith(
            color: colors.onSurfaceVariant,
            height: 1.4,
          ),
        ),
      ],
    );
  }
}

class _AccountSummaryCard extends StatelessWidget {
  const _AccountSummaryCard({
    required this.count,
    required this.totalBalanceCents,
  });

  final int count;
  final int totalBalanceCents;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF104E46),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Gesamtsaldo · manuell erfasst',
            style: TextStyle(color: Colors.white70, fontSize: 12),
          ),
          const SizedBox(height: 7),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              count == 0 ? '–' : formatEuro(totalBalanceCents / 100),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 27,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.8,
              ),
            ),
          ),
          const SizedBox(height: 3),
          Text(
            '$count ${count == 1 ? 'Konto' : 'Konten'} auf diesem Gerät',
            style: const TextStyle(color: Colors.white70, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _AccountCard extends StatelessWidget {
  const _AccountCard({
    required this.account,
    required this.enabled,
    required this.onEdit,
    required this.onDelete,
  });

  final Account account;
  final bool enabled;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;

    return Container(
      margin: const EdgeInsets.only(bottom: 9),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(
          color: colors.outlineVariant.withValues(alpha: 0.35),
        ),
      ),
      child: ListTile(
        onTap: enabled ? onEdit : null,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
        leading: CircleAvatar(
          backgroundColor: colors.primaryContainer,
          foregroundColor: colors.onPrimaryContainer,
          child: Icon(account.type.icon, size: 20),
        ),
        title: Text(
          account.name,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
        ),
        subtitle: Text(account.details, style: const TextStyle(fontSize: 11)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  formatEuro(account.balanceCents / 100),
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  account.type.label,
                  style: TextStyle(
                    color: colors.onSurfaceVariant,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            PopupMenuButton<String>(
              enabled: enabled,
              tooltip: 'Aktionen für ${account.name}',
              onSelected: (value) {
                if (value == 'edit') onEdit();
                if (value == 'delete') onDelete();
              },
              itemBuilder: (context) => const [
                PopupMenuItem(value: 'edit', child: Text('Bearbeiten')),
                PopupMenuItem(value: 'delete', child: Text('Löschen')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
