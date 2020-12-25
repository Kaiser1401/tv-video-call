echo "--------- $(date) ---------" >> vidlog.txt
while ! ping -c 1 -W 1 8.8.8.8; do
    echo "Waiting for 8.8.8.8 - network interface might be down..." >> vidlog.txt
    sleep 1
done
git checkout update
git pull
echo $VIDROOM
echo $VIDNAME
echo $VIDSERVER
python3 main.py --room $VIDROOM --user $VIDNAME --server $VIDSERVER >> vidlog.txt
