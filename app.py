import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
from fuzzywuzzy import process
from community import community_louvain
from sentence_transformers import SentenceTransformer

# Initialize the model for title similarity
model = SentenceTransformer('all-MiniLM-L6-v2')

# Upload data file
st.title('Enhanced Keyword Clustering with SERP Overlap and Titles')
uploaded_file = st.file_uploader("Upload your keyword CSV file", type=['csv'])

if uploaded_file:
    # Load data
    data = pd.read_csv(uploaded_file)
    
    # Field mapping
    keyword_col = st.selectbox('Select the Keyword column:', data.columns)
    impression_col = st.selectbox('Select the Impression column:', data.columns)
    position_col = st.selectbox('Select the Position column:', data.columns)
    url_cols = st.multiselect('Select the SERP URL columns:', [col for col in data.columns if 'URL' in col])
    title_col = st.selectbox('Select the Title column:', data.columns)
    
    # Deduplicate exact keyword matches by keeping the one with the highest impressions
    data = data.sort_values(by=impression_col, ascending=False).drop_duplicates(subset=keyword_col, keep='first')

    # Fuzzy Matching to clean similar keywords
    unique_keywords = data[keyword_col].unique()
    keyword_mapping = {kw: process.extractOne(kw, unique_keywords)[0] for kw in unique_keywords}
    data[keyword_col] = data[keyword_col].apply(lambda x: keyword_mapping[x])
    
    # Embed titles for semantic similarity
    data['title_embedding'] = data[title_col].apply(lambda x: model.encode(x))

    # Create a graph where nodes are keywords
    G = nx.Graph()
    
    # Add nodes
    for kw in data[keyword_col].unique():
        G.add_node(kw)
    
    # Add edges based on SERP URL overlap and title similarity
    for i, keyword1 in enumerate(data[keyword_col].unique()):
        urls1 = set(data[data[keyword_col] == keyword1][url_cols].values.flatten())
        title_embedding1 = data[data[keyword_col] == keyword1]['title_embedding'].values[0]
        for j, keyword2 in enumerate(data[keyword_col].unique()):
            if i < j:
                urls2 = set(data[data[keyword_col] == keyword2][url_cols].values.flatten())
                title_embedding2 = data[data[keyword_col] == keyword2]['title_embedding'].values[0]
                
                # SERP overlap calculation with position weighting
                positions1 = data[data[keyword_col] == keyword1][position_col].values[0]
                positions2 = data[data[keyword_col] == keyword2][position_col].values[0]
                overlap = sum([1 / (pos1 + pos2) for url, pos1, pos2 in zip(urls1.intersection(urls2), positions1, positions2)])
                
                # Semantic similarity of titles
                title_similarity = np.dot(title_embedding1, title_embedding2) / (np.linalg.norm(title_embedding1) * np.linalg.norm(title_embedding2))
                
                # Total weight: combine overlap and title similarity
                total_weight = overlap + title_similarity
                
                if total_weight > 0:
                    G.add_edge(keyword1, keyword2, weight=total_weight)
    
    # Apply Louvain community detection
    partition = community_louvain.best_partition(G, weight='weight')
    
    # Add cluster labels to the data
    data['cluster'] = data[keyword_col].map(partition)
    
    # Rename clusters based on the highest impression keyword
    cluster_names = {}
    for cluster_id in data['cluster'].unique():
        cluster_data = data[data['cluster'] == cluster_id]
        top_keyword = cluster_data.loc[cluster_data[impression_col].idxmax(), keyword_col]
        cluster_names[cluster_id] = top_keyword
        
    data['cluster_name'] = data['cluster'].map(cluster_names)
    
    # Display the results
    st.write('Clustered keywords:', data[[keyword_col, impression_col, 'cluster_name']])
    
    # Download the clustered keywords as a CSV file
    st.download_button(
        label="Download clustered keywords",
        data=data.to_csv(index=False),
        file_name='clustered_keywords.csv',
        mime='text/csv'
    )
