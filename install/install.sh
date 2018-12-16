#!/bin/bash
#

set -x

exec > >(sudo tee install.log)
exec 2>&1

echo "start installing....."
DIR=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)
source $DIR/install.conf
source /etc/lsb-release

sudo apt-get update -y || exit 1
sudo apt-get upgrade -y || exit 1
sudo apt-get install -y ntp ntpdate || exit 1

#if [[ "$INSTALL_WSGI" == "1" ]]; then
#sudo apt-get install -y libmysqlclient-dev mysql-client || exit 1
#fi

if [[ "$INSTALL_MYSQL_SERVER" == "1" ]]; then
sudo systemctl stop mysql.service
sudo apt-get remove --purge mysql-server mysql-client mysql-common -y
sudo apt-get autoremove -y
sudo apt-get autoclean
sudo rm -rf /etc/mysql
sudo rm -rf /var/lib/mysql
sudo rm -rf /var/lib/mysql-keyring
sudo rm -rf /var/lib/mysql-files
#sudo apt-get install -y  mysql-server || exit 1
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server || exit 1
sudo mysqladmin -u root password ${MYSQL_PASSWORD} || exit 1
sudo systemctl restart mysql.service
fi

if [[ "$INSTALL_WSGI" == "1" ]]; then
sudo apt-get install -y libmysqlclient-dev mysql-client || exit 1
fi

sudo apt-get install -y git python-pip python-setuptools python-tox python-dev gcc openssl || exit 1
if [[  "$INSTALL_WSGI" == "1" ]]; then
sudo apt-get install -y apache2 libapache2-mod-wsgi || exit 1
fi

cd ${USECASE_DIR}
if [[  "$INSTALL_WSGI" == "1" ]]; then
sudo pip install --upgrade pip
sudo pip install --upgrade tox pep8 setuptools
sudo pip install --upgrade -r requirements.txt -r test-requirements.txt || exit 1
sudo python setup.py install || exit 1
fi

for NTP_SERVER in $NTP_SERVERS; do
    sed -i "/prepend customized ntp servers above/i \
server $NTP_SERVER iburst" /etc/ntp.conf
    sed -i "/prepend customized ntp servers above/i \
$NTP_SERVER" /etc/ntp/step-tickers
done
sudo systemctl enable ntp.service
sudo systemctl stop ntp.service
sudo ntpdate $NTP_SERVERS || exit 1
sudo systemctl restart ntp.service
sudo systemctl status ntp.service
if [[ "$?" != "0" ]]; then
    echo "failed to restart ntpd"
    exit 1
else
    echo "ntpd is restarted"
fi

if [[ "$INSTALL_WSGI" == "1" ]]; then
    mkdir -p /var/log/usecase || exit 1
    chmod -R 777 /var/log/usecase || exit 1
    mkdir -p /var/cache/usecase || exit 1
    chmod -R 777 /var/cache/usecase || exit 1
    mkdir -p /etc/usecase || exit 1
    chmod -R 777 /etc/usecase || exit 1
    cp -rf conf/* /etc/usecase/ || exit 1
    mkdir -p /var/www/usecase_web || exit 1
    chmod -R 777 /var/www/usecase_web || exit 1
    cp -rf web/* /var/www/usecase_web/ | exit 1
fi

export MYSQL_SERVER=${MYSQL_SERVER:-"${MYSQL_SERVER_IP}:${MYSQL_SERVER_PORT}"}
if [[ "$INSTALL_WSGI" == "1" ]]; then
if [-f /etc/usecase/settings]; then
    sudo sed -i "s/DATABASE_TYPE\\s*=.*/DATABASE_TYPE = 'mysql'/g" /etc/usecase/settings
    sudo sed -i "s/DATABASE_USER\\s*=.*/DATABASE_USER = '$MYSQL_USER'/g" /etc/usecase/settings
    sudo sed -i "s/DATABASE_PASSWORD\\s*=.*/DATABASE_PASSWORD = '$MYSQL_PASSWORD'/g" /etc/usecase/settings
    sudo sed -i "s/DATABASE_SERVER\\s*=.*/DATABASE_SERVER = '$MYSQL_SERVER'/g" /etc/usecase/settings
    sudo sed -i "s/DATABASE_PORT\\s*=.*/DATABASE_PORT = $MYSQL_SERVER_PORT/g" /etc/usecase/settings
    sudo sed -i "s/DATABASE_NAME\\s*=.*/DATABASE_NAME = '$MYSQL_NAME'/g" /etc/usecase/settings
fi
fi

if [[ "$INSTALL_MYSQL_SERVER" == "1" ]]; then
sudo systemctl restart mysql.service
sudo systemctl status mysql.service
if [[ "$?" != "0" ]]; then
    echo "failed to restart mysql server"
    exit 1
else
    echo "mysql server is restarted"
fi
sudo mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} -e "show databases;" || exit 1
echo "mysql server access succeeded"

sudo mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} -e "GRANT ALL ON *.* to '${MYSQL_USER}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}'; flush privileges;" || exit 1
echo "mysql server privileges are updated"

sudo mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} -e "GRANT ALL ON *.* to '${MYSQL_USER}'@'${MYSQL_SERVER_IP}' IDENTIFIED BY '${MYSQL_PASSWORD}'; flush privileges;" || exit 1
echo "mysql server privileges are updated"

sudo mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'root';"
echo "mysql server privileges are updated"
sudo systemctl restart mysql.service
fi

if [[ "$INSTALL_WSGI" == "1" ]]; then
sudo mysql -h${MYSQL_IP} --port=${MYSQL_PORT} -u ${MYSQL_USER} -p${MYSQL_PASSWORD} -e "drop database [IF EXISTS] ${MYSQL_DATABASE};"
sudo mysql -h${MYSQL_IP} --port=${MYSQL_PORT} -u ${MYSQL_USER} -p${MYSQL_PASSWORD} -e "create database ${MYSQL_DATABASE};" || exit 1
echo "mysql database is created"

usecase-db-manage upgrade head || exit 1
echo "mysql database schema is setup"
fi

if [[ "$INSTALL_WSGI" == "1" ]]; then
cp -rf apache2/usecase.conf /etc/apache2/sites-available/ || exit 1
sudo a2enmod proxy || exit 1
sudo a2enmod rewrite || exit 1
sudo a2enmod ssl || exit 1
sudo a2enmod dir || exit 1
sudo a2enmod cache || exit 1
sudo a2enmod cache_disk || exit 1
sudo a2enmod status || exit 1
sudo a2enmod wsgi || exit 1
sudo a2ensite usecase || exit 1

sudo systemctl daemon-reload

sudo systemctl enable apache2.service
sudo systemctl restart apache2.service
sudo systemctl status apache2.service
if [[ "$?" != "0" ]]; then
    echo "failed to restart apache2"
    exit 1
else
    echo "apache2 is restarted"
fi
fi

if [[ "$INSTALL_SAMPLE_DB" == "1" ]]; then
sudo systemctl restart mysql.service
export MYSQL_PWD=${MYSQL_PASSWORD}
mysql -uroot ${MYSQL_DATABASE}<${SCRIPT_DIR}/${DATABASE_FILE}
fi


sleep 10
echo "install is done"
