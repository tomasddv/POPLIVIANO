"""Almacenamiento real: repositorio GitHub privado separado; fallback local en PC.

Streamlit Community Cloud no tiene un disco duradero. Para conservar cambios tras
reinicios se requiere DATA_GITHUB_REPO y DATA_GITHUB_TOKEN en st.secrets.
"""
from __future__ import annotations
import base64
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

from period_store import archive_bytes

ROOT=Path(__file__).resolve().parent
LOCAL=ROOT/'.local_store'
PREFIX='pop_ddv'
MAX_ZIP=35_000_000


def read_zip_assets(blob:bytes) -> dict[str,bytes]:
    result={}
    if not blob:return result
    if len(blob)>MAX_ZIP:raise ValueError('Archivo de imágenes demasiado grande.')
    with zipfile.ZipFile(BytesIO(blob)) as z:
        for item in z.infolist():
            if item.is_dir():continue
            if item.file_size>2_500_000:raise ValueError('Imagen individual demasiado grande.')
            name=item.filename
            if name.startswith(('pop/','remitos/')) and '..' not in name and name.lower().endswith('.jpg'):
                result[name]=z.read(item)
    return result


def write_zip_assets(assets:dict[str,bytes]) ->bytes:
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for key,binary in sorted(assets.items()):
            if key.startswith(('pop/','remitos/')) and key.endswith('.jpg'):
                z.writestr(key,binary)
    return stream.getvalue()


class StorageError(Exception):pass


class GitHubStore:
    def __init__(self, repo:str, token:str, branch:str='main'):
        if '/' not in repo or not repo.strip() or not token.strip():
            raise StorageError('Configurá DATA_GITHUB_REPO y DATA_GITHUB_TOKEN.')
        self.repo=repo.strip();self.token=token.strip();self.branch=branch.strip() or 'main'
        self.api='https://api.github.com/repos/'+self.repo

    def _call(self,method,path,data=None):
        url=self.api+path
        req=Request(url,method=method,headers={
            'Authorization':'Bearer '+self.token,
            'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
            'User-Agent':'pop-liviano-ddv/1.0',
            'Content-Type':'application/json'},
            data=json.dumps(data).encode('utf-8') if data is not None else None)
        try:
            with urlopen(req,timeout=25) as resp:return json.loads(resp.read())
        except HTTPError as e:
            if e.code==404 and method=='GET':return None
            if e.code in (401,403):msg='Token sin acceso al repositorio privado. Revisá permisos Contents (read/write).'
            elif e.code==409:msg='Se detectaron modificaciones concurrentes. Recargá el registro antes de guardar.'
            elif e.code==404:msg='Repositorio o rama no encontrados; revisá DATA_GITHUB_REPO y DATA_GITHUB_BRANCH.'
            else:msg=f'GitHub respondió HTTP {e.code}.'
            raise StorageError(msg) from e
        except Exception as e:raise StorageError(f'No se pudo acceder a GitHub: {e}') from e

    def _get(self,key):
        path='/contents/'+quote(f'{PREFIX}/{key}',safe='/')+'?'+urlencode({'ref':self.branch})
        obj=self._call('GET',path)
        if obj is None:return None,None
        sha=obj.get('sha')
        if obj.get('content') and obj.get('encoding')=='base64':
            binary=base64.b64decode(obj['content']);return binary,sha
        # Para archivos de > 1 MB, la API de Contents no devuelve contenido.
        blob=self._call('GET','/git/blobs/'+sha)
        if not blob or blob.get('encoding')!='base64':
            raise StorageError('GitHub no devolvió el archivo de imágenes.')
        return base64.b64decode(blob['content']),sha

    def _put(self,key,binary,msg):
        old,sha=self._get(key)
        data={'message':msg,'content':base64.b64encode(binary).decode('ascii'),'branch':self.branch}
        if sha:data['sha']=sha
        self._call('PUT','/contents/'+quote(f'{PREFIX}/{key}',safe='/'),data)

    def load(self):return self._get('registro.json')[0]
    def load_assets(self,label):
        data,_=self._get(f'assets/{label.replace(" ","_")}.zip')
        return read_zip_assets(data) if data else None
    def save(self,periods,assets,dirty):
        for label in dirty:
            self._put(f'assets/{label.replace(" ","_")}.zip',write_zip_assets(assets.get(label,{})),
                      f'POP DDV: actualizar imágenes {label}')
        self._put('registro.json',archive_bytes(periods),'POP DDV: guardar registro y controles')


class LocalStore:
    """Persistencia para desarrollo en PC. NO duradera en Community Cloud."""
    def load(self):
        path=LOCAL/'registro.json';return path.read_bytes() if path.exists() else None
    def load_assets(self,label):
        path=LOCAL/'assets'/f'{label.replace(" ","_")}.zip'
        return read_zip_assets(path.read_bytes()) if path.exists() else None
    def save(self,periods,assets,dirty):
        (LOCAL/'assets').mkdir(parents=True,exist_ok=True)
        for label in dirty:
            target=LOCAL/'assets'/f'{label.replace(" ","_")}.zip'
            tmp=target.with_suffix('.zip.tmp');tmp.write_bytes(write_zip_assets(assets.get(label,{})));tmp.replace(target)
        target=LOCAL/'registro.json';tmp=target.with_suffix('.json.tmp')
        tmp.write_bytes(archive_bytes(periods));tmp.replace(target)


def make_store(secrets):
    repo=str(secrets.get('DATA_GITHUB_REPO','') or '').strip()
    token=str(secrets.get('DATA_GITHUB_TOKEN','') or '').strip()
    if bool(repo)!=bool(token):return LocalStore(),'incompleto'
    if repo and token:return GitHubStore(repo,token,str(secrets.get('DATA_GITHUB_BRANCH','main'))),'github'
    return LocalStore(),'local'
