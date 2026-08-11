# Timeline privato cifrato

Questa cartella contiene l'export originale Google Timeline, compresso e
cifrato. Non contiene la password.

Il file è scaricabile direttamente da
`/vita/spostamenti/data/private/Timeline.json.gz.aes256gcm` oppure tramite clone
del repository.

## Decifrare

Servono Python 3 e `cryptography`:

```powershell
pip install cryptography
python tools/vita_private_archive.py decrypt `
  --input vita/spostamenti/data/private/Timeline.json.gz.aes256gcm `
  --output Timeline.json
```

Lo script chiede la password senza mostrarla. Al termine verifica lo SHA-256 del
JSON. Condividere la password separatamente dal link GitHub.

Per controllare password, autenticità e hash senza scrivere il JSON in chiaro:

```powershell
python tools/vita_private_archive.py verify `
  --input vita/spostamenti/data/private/Timeline.json.gz.aes256gcm
```

## Formato e sicurezza

- gzip prima della cifratura;
- AES-256-GCM con autenticazione del contenuto e dell'intestazione;
- chiave derivata dalla password con scrypt (`N=131072`, `r=8`, `p=1`);
- salt e nonce casuali per ogni nuova cifratura;
- SHA-256 originale incorporato nell'intestazione autenticata.

Il repository è pubblico: chiunque può scaricare il file cifrato e tentare un
attacco offline. La password non deve essere salvata nel repository e va cambiata
rigenerando l'archivio se viene condivisa accidentalmente.
