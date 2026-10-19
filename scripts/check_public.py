"""Check Git publication candidates, history, and build output without printing secrets.

This is a project guard, not a guarantee that arbitrary sensitive content can be
recognized. It reports locations/categories only. Git identity is checked by
default; --files-only leaves the explicitly deferred identity decision separate.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
LOCAL_ROOTS={'.env','.jev-image-data','.photo','photos','data','node_modules','dist','.venv','.aws','.codex','.ssh','.config','.git'}
SECRET_NAMES={'TYPESAFE_API_KEY','HUGGING_FACE_API','HF_TOKEN','KAGGLE_KEY','KAGGLE_API_TOKEN','GITHUB_TOKEN','GH_TOKEN','OPENAI_API_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'}
PATTERNS={
    'credential-format':re.compile(r'(?:hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'),
    'personal-home-path':re.compile(r'(?:[/]home/[^/\s"\']+|[/]mnt/[a-z]/Users/[^/\r\n"\']+|[A-Za-z]:\\Users\\[^\\\r\n"\']+)'),
}


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],capture_output=True,check=True).stdout


def local_secrets(root):
    values={name:os.environ[name] for name in SECRET_NAMES if os.environ.get(name)}
    path=root/'.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            name,value=line.split('=',1)
            if any(part in name.upper() for part in ['KEY','TOKEN','SECRET','PASSWORD']):
                # Check file values as well as shell overrides; either can leak.
                values['dotenv:'+name.strip()]=value.strip().strip('"\'')
    return {name:value for name,value in values.items() if len(value)>=8 and not value.lower().startswith(('your_','placeholder'))}


def private_path(name):
    path=Path(name)
    if path.parts and path.parts[0] in LOCAL_ROOTS:return True
    if path.name.startswith('.env') and path.name!='.env.example':return True
    if path.name in {'kaggle.json','credentials.json','.netrc','.pypirc'}:return True
    if path.suffix.lower() in {'.pem','.key','.p12','.pfx','.sqlite','.sqlite3','.db','.dump','.zip'}:return True
    if path.parts and path.parts[0] in {'.agent','.agents','.claude'}:
        return len(path.parts)<2 or path.parts[1] not in {'skills','CLAUDE.md'}
    return False


def inspect_content(name,data,secrets,username=''):
    findings=[]
    if any(value.encode() in data for value in secrets.values()):
        findings.append({'path':name,'kind':'exact-local-credential'})
    try:text=data.decode('utf-8')
    except UnicodeError:
        return findings+[{'path':name,'kind':'binary-content-needs-review'}]
    for number,line in enumerate(text.splitlines(),1):
        for kind,pattern in PATTERNS.items():
            if pattern.search(line):findings.append({'path':name,'line':number,'kind':kind})
        if username and re.search(r'(?<!\w)'+re.escape(username)+r'(?!\w)',line,re.I):
            findings.append({'path':name,'line':number,'kind':'local-username'})
    return findings


def audit(root=ROOT, files_only=False, all_refs=False):
    root=root.resolve()
    secrets=local_secrets(root)
    username=getpass.getuser()
    if len(username)<4 or username.lower() in {'root','user','admin','runner'}:username=''
    findings=[]
    names=sorted(set(name for name in git(root,'ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0') if name))
    for name in names:
        path=root/name
        if private_path(name):findings.append({'path':name,'kind':'private-file-in-publication-set'})
        if path.is_symlink():
            target=os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(root):
                findings.append({'path':name,'kind':'nonportable-or-external-symlink'})
        elif path.is_file():findings.extend(inspect_content(name,path.read_bytes(),secrets,username))
    # Cached/index content may differ from worktree files after a secret was removed.
    for record in git(root,'ls-files','--stage','-z').decode().split('\0'):
        if not record:continue
        fields,name=record.split('\t',1)
        mode,blob,stage=fields.split()
        findings.extend(inspect_content('index:'+name,git(root,'cat-file','blob',blob),secrets,username))
    public_refs=git(root,'for-each-ref','--format=%(refname)','refs/heads','refs/tags').decode().splitlines()
    head=subprocess.run(['git','-C',str(root),'rev-parse','--verify','HEAD^{commit}'],capture_output=True,text=True)
    revisions=list(public_refs)
    if head.returncode==0:revisions.append(head.stdout.strip())
    local_refs=[name for name in git(root,'for-each-ref','--format=%(refname)').decode().splitlines() if not name.startswith(('refs/heads/','refs/tags/'))]
    object_args=['--all'] if all_refs else revisions
    objects=git(root,'rev-list','--objects',*object_args,'--').decode().splitlines() if object_args else []
    history_blobs=0
    for record in objects:
        blob,_,name=record.partition(' ')
        if not name or git(root,'cat-file','-t',blob).strip()!=b'blob':continue
        history_blobs+=1
        if private_path(name):findings.append({'path':'history:'+name,'kind':'historical-private-file'})
        findings.extend(inspect_content('history:'+name,git(root,'cat-file','blob',blob),secrets,username))
    for path in (root/'dist').rglob('*'):
        if path.is_file():findings.extend(inspect_content('build:'+path.relative_to(root).as_posix(),path.read_bytes(),secrets,username))
    if not files_only:
        configured=subprocess.run(['git','-C',str(root),'config','--get','user.email'],capture_output=True,text=True).stdout.strip()
        if not configured.endswith('@users.noreply.github.com'):
            findings.append({'path':'git-config','kind':'public-commit-identity-not-configured','note':'Choose a public display name and GitHub noreply address before committing; values are not printed.'})
        commits=git(root,'log','--format=%H%x09%ae%x09%ce',*revisions,'--').decode().splitlines() if revisions else []
        for record in commits:
            commit,author,committer=record.split('\t')
            if not all(value.endswith('@users.noreply.github.com') for value in [author,committer]):
                findings.append({'path':'commit:'+commit[:12],'kind':'historical-public-email-needs-review'})
    return {'publicationFiles':len(names),'historyBlobs':history_blobs,'identityChecked':not files_only,
            'historyScope':'all local refs' if all_refs else 'branches, tags, and current HEAD',
            'localOnlyRefs':len(local_refs),'findings':findings}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files-only',action='store_true')
    parser.add_argument('--all-refs',action='store_true',help='Also inspect private tool snapshots; never mirror local refs to a public repository.')
    args=parser.parse_args()
    result=audit(files_only=args.files_only,all_refs=args.all_refs)
    print(json.dumps(result,indent=2))
    return 1 if result['findings'] else 0


if __name__=='__main__':raise SystemExit(main())
