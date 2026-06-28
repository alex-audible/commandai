# `ai` command gallery

A grab-bag of things you can ask `commandai`. You type the **plain-English line**;
the tool proposes the shell command (with a per-argument explanation), you confirm
with arrow keys + Enter, and it runs in your current shell.

The `# →` line under each example shows the kind of command the model typically
produces on macOS/zsh. Your exact result may differ — that's the point: it's
generated for *your* current directory and context, and you always review it
before it runs.

> Tip: nothing runs until you confirm. Add `-n`/`--dry-run` to only preview,
> `-y`/`--yes` to skip the prompt. Destructive commands ask for an extra confirm.

---

## Files & directories

```bash
ai list everything here including hidden files, newest first
# → ls -lath

ai find the 5 largest files in this folder
# → du -ah . | sort -rh | head -n 5

ai how big is this directory
# → du -sh .

ai count how many python files are in this project
# → find . -name '*.py' | wc -l

ai make a folder called build and an empty file inside it called .keep
# → mkdir -p build && touch build/.keep

ai show me a tree of this directory two levels deep
# → find . -maxdepth 2 -print | sed -e 's;[^/]*/;  ;g'
```

## Finding things

```bash
ai find every file changed in the last 24 hours
# → find . -type f -mtime -1

ai search all the source files for the word TODO
# → grep -rn "TODO" .

ai find files bigger than 100 megabytes under my home folder
# → find ~ -type f -size +100M

ai which files contain the string "API_KEY"
# → grep -rln "API_KEY" .
```

## Archives & compression

```bash
ai create a gzipped tarball of the src folder
# → tar -czf src.tar.gz src

ai extract this archive
# → tar -xzf archive.tar.gz

ai zip up all the pdfs in this folder
# → zip pdfs.zip *.pdf

ai how do I see what's inside a tarball without extracting it
# → tar -tzf archive.tar.gz
```

## Media — ffmpeg, images, audio

```bash
ai use ffmpeg to convert all the videos in this folder from mov to mp4
# → for f in *.mov; do ffmpeg -i "$f" "${f%.mov}.mp4"; done

ai extract the audio from video.mp4 as an mp3
# → ffmpeg -i video.mp4 -q:a 0 -map a video.mp3

ai resize all the jpgs in this folder to 1080px wide
# → for f in *.jpg; do sips --resampleWidth 1080 "$f"; done

ai make a 10 second clip starting at 1 minute into movie.mp4
# → ffmpeg -ss 00:01:00 -i movie.mp4 -t 10 -c copy clip.mp4

ai convert this png to a jpg
# → sips -s format jpeg image.png --out image.jpg
```

## Homebrew & installing tools (uses web search)

When you describe a tool instead of naming it, the model can search the web to
find the right Homebrew formula or cask.

```bash
ai brew install a tool that flashes bootable images to usb drives
# → brew install --cask balenaetcher

ai install a command line tool for pretty-printing json
# → brew install jq

ai install a faster alternative to grep
# → brew install ripgrep

ai update all my homebrew packages
# → brew update && brew upgrade
```

## Git

```bash
ai stage everything and commit with the message initial commit
# → git add -A && git commit -m "initial commit"

ai undo the last commit but keep my changes
# → git reset --soft HEAD~1

ai show me what changed in the last commit
# → git show HEAD

ai discard all my uncommitted changes
# → git checkout -- .        (flagged: destructive — asks to confirm)

ai create and switch to a new branch called feature/login
# → git switch -c feature/login
```

## Fixing the last command (shell-context aware)

After a command fails, `ai` can see its exit code and your recent history, so you
can just ask it to fix what went wrong.

```bash
$ git push
 ! [rejected] main -> main (fetch first)
$ ai fix that
# → git pull --rebase && git push

$ tar -xzf backup.tar
 gzip: stdin: not in gzip format
$ ai fix that
# → tar -xf backup.tar        # the file wasn't gzipped

$ pip install reqests
$ ai did that fail because of a typo
# → pip install requests
```

## System & processes

```bash
ai what's using port 3000
# → lsof -i :3000

ai kill the process running on port 8080
# → lsof -ti :8080 | xargs kill      (flagged: asks to confirm)

ai show the top 10 processes by memory
# → ps aux | sort -rk 4 | head -n 10

ai how much free disk space do I have
# → df -h

ai show my mac's cpu and memory info
# → sysctl -n machdep.cpu.brand_string && sysctl hw.memsize
```

## Networking

```bash
ai what's my local ip address
# → ipconfig getifaddr en0

ai what's my public ip address
# → curl -s ifconfig.me

ai download this file and save it as report.pdf
# → curl -L -o report.pdf <url>

ai check if google is reachable
# → ping -c 4 google.com
```

## Text & data processing

```bash
ai pretty print this json file
# → jq . data.json

ai show me the first 20 lines of access.log
# → head -n 20 access.log

ai count the unique values in the second column of data.csv
# → cut -d, -f2 data.csv | sort | uniq -c

ai replace every tab with two spaces in config.txt
# → sed -i '' 's/\t/  /g' config.txt      (flagged: modifies the file)
```

## Permissions & ownership

```bash
ai make deploy.sh executable
# → chmod +x deploy.sh

ai who owns the files in this directory
# → ls -l

ai give read and write to everyone for notes.txt
# → chmod 666 notes.txt
```

---

## Handy flags

| Flag | What it does |
|---|---|
| `-n`, `--dry-run` | Show the suggestion(s) without running anything |
| `-y`, `--yes` | Run the first suggestion without prompting |
| `--no-web` | Don't let the model search the web this time |
| `--no-context` | Don't send the directory listing (useful in huge/irrelevant folders) |
| `--no-shell-context` | Don't send the previous command / exit code / history |
| `--print-config` | Print the resolved config (model, endpoint, …) and exit |
| `--model NAME` | Use a different model just for this run |

See the [README](README.md) for setup, configuration, and how it all works.
