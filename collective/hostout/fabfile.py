import os
import os.path
from fabric import api, contrib
from collective.hostout.hostout import buildoutuser
from fabric.context_managers import cd
from pkg_resources import resource_filename


def setupusers():
    """ create users if needed """

    hostout = api.env.get('hostout')
    buildout = api.env['buildout-user']
    effective = api.env['effective-user']
    buildoutgroup = api.env['buildout-group']
    owner = buildout
    
    api.sudo('groupadd %(buildoutgroup)s || echo "group exists"' % locals())
    addopt = "--no-user-group -M -g %(buildoutgroup)s" % locals()
    api.sudo('egrep ^%(owner)s: /etc/passwd || useradd %(owner)s %(addopt)s' % locals())
    api.sudo('egrep ^%(effective)s: /etc/passwd || useradd %(effective)s %(addopt)s' % locals())
    api.sudo('gpasswd -a %(owner)s %(buildoutgroup)s' % locals())
    api.sudo('gpasswd -a %(effective)s %(buildoutgroup)s' % locals())


    #Copy authorized keys to buildout user:
    key_filename, key = api.env.hostout.getIdentityKey()
    for owner in [api.env['buildout-user']]:
        api.sudo("mkdir -p ~%(owner)s/.ssh" % locals())
        api.sudo('touch ~%(owner)s/.ssh/authorized_keys'%locals() )
        contrib.files.append(key, '~%(owner)s/.ssh/authorized_keys'%locals(), use_sudo=True)
        #    api.sudo("echo '%(key)s' > ~%(owner)s/.ssh/authorized_keys" % locals())
        api.sudo("chown -R %(owner)s ~%(owner)s/.ssh" % locals() )
    

def setowners():
    """ Ensure ownership and permissions are correct on buildout and cache """
    hostout = api.env.get('hostout')
    buildout = api.env['buildout-user']
    effective = api.env['effective-user']
    buildoutgroup = api.env['buildout-group']
    owner = buildout


    path = api.env.path
    bc = hostout.buildout_cache
    dl = hostout.getDownloadCache()
    dist = os.path.join(dl, 'dist')
    bc = hostout.getEggCache()
    var = os.path.join(path, 'var')
    
    # What we want is for
    # - login user to own the buildout and the cache.
    # - effective user to be own the var dir + able to read buildout and cache.
    
    api.sudo('chown -R %(buildout)s:%(buildoutgroup)s %(path)s && '
             ' chmod -R u+rw,g+r-w,o-rw %(path)s' % locals())
    api.sudo('chmod g+x `find %(path)s -perm -u+x`' % locals()) #so effective can execute code
    api.sudo('chmod g+s `find %(path)s -type d`' % locals()) # so new files will keep same group
    api.sudo('mkdir -p %(var)s && chown -R %(effective)s:%(buildoutgroup)s %(var)s && '
             ' chmod -R u+rw,g+wrs,o-rw %(var)s ' % locals())
    
    for cache in [bc, dl, bc]:
        #HACK Have to deal with a shared cache. maybe need some kind of group
        api.sudo('mkdir -p %(cache)s && chown -R %(buildout)s:%(buildoutgroup)s %(cache)s && '
                 ' chmod -R u+rw,a+r %(cache)s ' % locals())


def initcommand(cmd):
    if cmd in ['uploadeggs','uploadbuildout','buildout','run']:
        api.env.user = api.env.hostout.options['buildout-user']
    else:
        api.env.user = api.env.hostout.options['user']
    key_filename = api.env.get('identity-file')
    if key_filename and os.path.exists(key_filename):
        api.env.key_filename = key_filename

def deploy():
    "predeploy, uploadeggs, uploadbuildout, buildout and then postdeploy"
    hostout = api.env['hostout']
    hostout.predeploy()
    hostout.uploadeggs()
    hostout.uploadbuildout()
    hostout.buildout()
    hostout.postdeploy()

def predeploy():
    """Perform any initial plugin tasks. Call bootstrap if needed"""
    hostout = api.env['hostout']

    #run('export http_proxy=localhost:8123') # TODO get this from setting

    path = api.env.path
    api.env.cwd = ''

    #if not contrib.files.exists(hostout.options['path'], use_sudo=True):
    try:
        api.sudo("ls  %(path)s/bin/buildout " % locals(), pty=True)
    except:
        hostout.bootstrap()
        hostout.setowners()
    

    api.env.cwd = api.env.path
    for cmd in hostout.getPreCommands():
        api.sudo('sh -c "%s"'%cmd)
    api.env.cwd = ''



    #Login as user plone
#    api.env['user'] = api.env['effective-user']


BUILDOUT = """
[buildout]
extends =
      src/base.cfg
      src/readline.cfg
      src/libjpeg.cfg
      src/python%(majorshort)s.cfg
      src/links.cfg

parts =
      ${buildout:base-parts}
      ${buildout:readline-parts}
      ${buildout:libjpeg-parts}
      ${buildout:python%(majorshort)s-parts}
      ${buildout:links-parts}

# ucs4 is needed as lots of eggs like lxml are also compiled with ucs4 since most linux distros compile with this      
[python-%(major)s-build:default]
extra_options +=
    --enable-unicode=ucs4
      
"""


def bootstrap():
#    api.env.hostout.setupusers()

    # bootstrap assumes that correct python is already installed
    path = api.env.path
    buildout = api.env['buildout-user']
    buildoutgroup = api.env['buildout-group']
    api.sudo('mkdir -p %(path)s' % locals())
    api.sudo('chown -R %(buildout)s:%(buildoutgroup)s %(path)s'%locals())

    buildoutcache = api.env['buildout-cache']
    api.sudo('mkdir -p %s/eggs' % buildoutcache)
    api.sudo('mkdir -p %s/downloads/dist' % buildoutcache)
    api.sudo('mkdir -p %s/extends' % buildoutcache)
    api.sudo('chown -R %s:%s %s' % (buildout, buildoutgroup, buildoutcache))
    api.env.cwd = api.env.path
   
    bootstrap = resource_filename(__name__, 'bootstrap.py')
    api.put(bootstrap, '%s/bootstrap.py' % path)
    
    # put in simplest buildout to get bootstrap to run
    api.sudo('echo "[buildout]" > buildout.cfg')

    version = api.env['python-version']
    major = '.'.join(version.split('.')[:2])

    api.sudo('python%(major)s bootstrap.py --distribute' % locals())
    api.env.hostout.setowners()

def bootstrapsource():
    path = api.env.path
    try:
        api.sudo("test -e  %(path)s/bin/buildout " % locals(), pty=True)
        return
    except:
        pass

    hostout = api.env.get('hostout')
    buildout = api.env['buildout-user']
    effective = api.env['effective-user']
    buildoutgroup = api.env['buildout-group']

    hostout.setupusers()
    api.sudo('mkdir -p %(path)s' % locals())
    hostout.setowners()

    version = api.env['python-version']
    major = '.'.join(version.split('.')[:2])
    majorshort = major.replace('.','')
    api.sudo('mkdir -p /var/buildout-python')

    with cd('/var/buildout-python'):
        #api.sudo('wget http://www.python.org/ftp/python/%(major)s/Python-%(major)s.tgz'%locals())
        #api.sudo('tar xfz Python-%(major)s.tgz;cd Python-%(major)s;./configure;make;make install'%locals())

        api.sudo('svn co http://svn.plone.org/svn/collective/buildout/python/')
        with cd('python'):
            api.sudo('curl -O http://python-distribute.org/distribute_setup.py')
            api.sudo('python distribute_setup.py')
            api.sudo('python bootstrap.py --distribute')
            contrib.files.append(BUILDOUT%locals(), 'buildout.cfg', use_sudo=True)
            api.sudo('bin/buildout')
        
    api.env.cwd = api.env.path
    api.sudo('wget -O bootstrap.py http://python-distribute.org/bootstrap.py')
    api.sudo('echo "[buildout]" > buildout.cfg')
    api.sudo('source /var/buildout-python/python/python-%(major)s/bin/activate; python bootstrap.py --distribute' % locals())
    api.sudo('chown -R %(buildout)s:%(buildoutgroup)s /var/buildout-python '%locals())

    #ensure bootstrap files have correct owners
    hostout.setowners()

    


def _bootstrap():
    """Install python,users and buildout"""
    hostout = api.env['hostout']

    raise Exception("Generic bootstrap unimplemented. Look for plugins")


    unified='Plone-3.2.1r3-UnifiedInstaller'
    unified_url='http://launchpad.net/plone/3.2/3.2.1/+download/Plone-3.2.1r3-UnifiedInstaller.tgz'

    sudo('mkdir -p %(dc)s/dist && sudo chmod -R a+rw  %(dc)s'%dict(dc=api.env.download_cache) )
    sudo(('mkdir -p %(dc)s && sudo chmod -R a+rw  %(dc)s') % dict(dc=hostout.getEggCache()) )

    #install prerequsites
    #sudo('which g++ || (sudo apt-get -ym update && sudo apt-get install -ym build-essential libssl-dev libreadline5-dev) || echo "not ubuntu"')

    #Download the unified installer if we don't have it
    buildout_dir=api.env.hostout.options['path']
    dist_dir = api.env.download_cache
    sudo('test -f %(buildout_dir)s/bin/buildout || '
         'test -f %(dist_dir)s/%(unified)s.tgz || '
         '( cd /tmp && '
         'wget  --continue %(unified_url)s '
         '&& sudo mv /tmp/%(unified)s.tgz %(dist_dir)s/%(unified)s.tgz '
#         '&& sudo chown %(effectiveuser)s %(dist_dir)s/%(unified)s.tgz '+
        ')' % locals() )
         
    # untar and run unified installer
    install_dir, instance =os.path.split(buildout_dir)
    effectiveuser = api.env['effective-user']
    sudo(('test -f %(buildout_dir)s/bin/buildout || '+
          '(cd /tmp && '+
          'tar -xvf %(dist_dir)s/%(unified)s.tgz && '+
          'test -d /tmp/%(unified)s && '+
          'cd /tmp/%(unified)s && '+
          'sudo mkdir -p  %(install_dir)s && '+
          'sudo ./install.sh --target=%(install_dir)s --instance=%(instance)s --user=%(effectiveuser)s --nobuildout standalone && '+
          'sudo chown -R %(effectiveuser)s %(install_dir)s/%(instance)s)') % locals()
          )
    api.env.cwd = hostout.remote_dir
    api.sudo('bin/buildout ')


@buildoutuser
def uploadeggs():
    """Release developer eggs and send to host """
    
    hostout = api.env['hostout']

    #need to send package. cycledown servers, install it, run buildout, cycle up servers

    dl = hostout.getDownloadCache()
    contents = api.run('ls %(dl)s/dist'%locals()).split()
    buildout = api.env.hostout.options['buildout-user']

    for pkg in hostout.localEggs():
        name = os.path.basename(pkg)
        if name not in contents:
            tmp = os.path.join('/tmp', name)
            tgt = os.path.join(dl, 'dist', name)
            api.put(pkg, tmp)
            api.run("mv -f %(tmp)s %(tgt)s && "
                    "chown %(buildout)s %(tgt)s && "
                    "chmod a+r %(tgt)s" % locals() )
@buildoutuser
def uploadbuildout():
    """Upload buildout pinned version of buildouts to host """
    hostout = api.env.hostout
    buildout = api.env['buildout-user']

    package = hostout.getHostoutPackage()
    tmp = os.path.join('/tmp', os.path.basename(package))
    tgt = os.path.join(hostout.getDownloadCache(), 'dist', os.path.basename(package))

    #api.env.warn_only = True
    if api.run("test -f %(tgt)s || echo 'None'" %locals()) == 'None' :
        api.put(package, tmp)
        api.run("mv %(tmp)s %(tgt)s" % locals() )
        #sudo('chown $(effectiveuser) %s' % tgt)


    user=hostout.options['buildout-user']
    install_dir=hostout.options['path']
    with cd(install_dir):
        api.run('tar -p -xvf %(tgt)s' % locals())
    
@buildoutuser
def buildout():
    """Run the buildout on the remote server """

    hostout = api.env.hostout
    hostout_file=hostout.getHostoutFile()
    #api.env.user = api.env['effective-user']
    api.env.cwd = hostout.remote_dir
    api.run('bin/buildout -c %(hostout_file)s' % locals())
    #api.sudo('sudo -u $(effectiveuser) sh -c "export HOME=~$(effectiveuser) && cd $(install_dir) && bin/buildout -c $(hostout_file)"')

#    sudo('chmod 600 .installed.cfg')
#    sudo('find $(install_dir)  -type d -name var -exec chown -R $(effectiveuser) \{\} \;')
#    sudo('find $(install_dir)  -type d -name LC_MESSAGES -exec chown -R $(effectiveuser) \{\} \;')
#    sudo('find $(install_dir)  -name runzope -exec chown $(effectiveuser) \{\} \;')
    hostout.setowners()



def postdeploy():
    """Perform any final plugin tasks """
    
    hostout = api.env.get('hostout')

    api.env.cwd = api.env.path
    hostout_file=hostout.getHostoutFile()
    sudoparts = hostout.options.get('sudo-parts',None)
    if sudoparts:
        api.sudo('bin/buildout -c %(hostout_file)s install %(sudoparts)s' % locals())

 
    api.env.cwd = api.env.path
    for cmd in hostout.getPostCommands():
        api.sudo('sh -c "%s"'%cmd)

@buildoutuser
def run(*cmd):
    """Execute cmd on remote as login user """
    api.env.cwd = api.env.path
    api.run(' '.join(cmd))

def sudo(*cmd):
    """Execute cmd on remote as root user """
    api.env.cwd = api.env.path
    api.sudo(' '.join(cmd))


