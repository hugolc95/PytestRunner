# PySide6 x64 branch

Architecture cible:

- `PytestRunner.exe`: Python 3.13 x64 + PySide6 / Qt 6.
- Execution pytest: processus externe utilisant l'interpreteur configure dans le Runner.
- Le Python de tests peut rester Python 3.13 x86 pour les DLL/SDK smart-card 32 bits.
- L'EXE n'embarque ni pytest ni les dependances propres aux tests.

## Build

Utiliser un Python 64 bits puis lancer:

```bat
build_exe.bat
```

Le script refuse un Python de build 32 bits et produit:

```text
dist\PytestRunner\PytestRunner.exe
```

## Machine cible

La machine cible n'a pas besoin d'un Python 64 bits installe pour lancer l'EXE.
Elle doit seulement disposer du runtime Python utilise pour les tests (x86 dans
le cas smart-card actuel), avec pytest et les dependances du workspace.

## Validation de migration

Le workflow GitHub Actions de cette branche:

1. utilise Python 3.13 x64;
2. installe PySide6 sans PyQt5;
3. execute la suite `runner/tests` avec Qt en mode offscreen;
4. construit l'EXE PyInstaller;
5. demarre l'EXE et verifie qu'il reste actif;
6. publie le dossier construit comme artefact.

La branche reste separee de `main` tant que la parite fonctionnelle n'est pas
validee.
