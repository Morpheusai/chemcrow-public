## install
```python
# 推荐使用python3.10
conda create -n chemcrow-molly python==3.10
cd chemcrow-molly
python setup.py install
```

## 替换paperscraper-lib.py
```
cp fix_package/lib.py $conda_path/lib/python3.10/site-packages/paperscraper/lib.py
```

## run
```
streamlit run molly.py --server.port xxx --server.address 0.0.0.0
```