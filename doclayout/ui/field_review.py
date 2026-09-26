"""Read-only, two-way PDF block evidence viewer. No model calls on interaction."""

import base64

import streamlit as st
import streamlit.components.v2

from doclayout.fields import leaves
from doclayout.ui.documents import Upload, preview
from doclayout.ui.exports import image_bytes
from doclayout.ui.field_summary import display_value, field_label

viewer = st.components.v2.component(
    "doclayout_field_evidence",
    html='<div class="layout"><div class="fields"></div><div class="paper"><img alt="Source document page"><svg aria-label="Evidence regions"></svg></div></div>',
    css="""
    .layout {display:grid;grid-template-columns: minmax(240px, 1fr) minmax(0, 2fr);gap:16px}
    .fields {max-height:850px;overflow:auto;min-width:0} button {font:inherit;text-align:left;overflow-wrap:anywhere;
      display:block;width:100%;padding:8px;margin-bottom:4px;color:var(--st-text-color);
      background:var(--st-background-color);border:1px solid var(--st-border-color);cursor:pointer}
    button.active {outline:2px solid var(--st-primary-color)} small {display:block;white-space:pre-wrap}
    .paper {position:relative;align-self:start;min-width:0} img {width:100%;display:block}
    svg {position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
    rect {fill:transparent;stroke:#ac6200;stroke-width:1;pointer-events:all;cursor:pointer}
    rect.active {fill:#ffc80055;stroke:#ef6500;stroke-width:2}
    @media(max-width:700px){.layout {grid-template-columns:1fr}}
    """,
    js="""
    export default function({data,parentElement,setStateValue}) {
      const list=parentElement.querySelector('.fields'), svg=parentElement.querySelector('svg');
      list.replaceChildren(); svg.replaceChildren();
      parentElement.querySelector('img').src=data.image;
      svg.setAttribute('viewBox',data.bounds.join(' '));
      let locked=data.selected || null;
      const nodes=[];
      const paint=(path)=>nodes.forEach(n=>n.node.classList.toggle('active',n.paths.includes(path)));
      const select=(path)=>{locked=locked===path?null:path;paint(locked);setStateValue('selected',locked);};
      for(const field of data.fields){
        const button=document.createElement('button'); button.type='button';
        const title=document.createElement('strong'); title.textContent=field.label;
        const value=document.createElement('span'); value.textContent=': '+String(field.value);
        button.append(title,value);
        for(const quote of field.quotes){const q=document.createElement('small');q.textContent=quote;button.append(q);}
        button.onmouseenter=()=>paint(field.path); button.onmouseleave=()=>paint(locked);
        button.onfocus=()=>paint(field.path);button.onblur=()=>paint(locked);
        button.onclick=()=>select(field.path);list.append(button);nodes.push({node:button,paths:[field.path]});
      }
      for(const region of data.regions){
        const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
        const [x,y,right,bottom]=region.bbox;
        Object.entries({x,y,width:right-x,height:bottom-y,tabindex:0,role:'button','aria-label':region.labels.join(', ')}).forEach(([k,v])=>rect.setAttribute(k,String(v)));
        const hover=()=>{paint(region.paths[0]);for(const n of nodes)if(n.paths.some(p=>region.paths.includes(p)))n.node.classList.add('active');};
        rect.onmouseenter=hover;rect.onmouseleave=()=>paint(locked);rect.onfocus=hover;
        rect.onclick=()=>select(region.paths[0]);
        rect.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(region.paths[0]);}};
        svg.append(rect);nodes.push({node:rect,paths:region.paths});
      }
      paint(locked);
    }
    """,
)


def show_evidence(store, document, record):
    """Render saved fields and their PDF block regions without model calls.

    Args:
        store (FieldStore): Local artifact owner.
        document (dict): Saved document with its preview manifest.
        record (dict): Grounded fields and evidence with page/box locations.

    Returns:
        None: Writes Streamlit controls and a bidirectional evidence component.
    """
    manifest = document["manifest"]
    field_values = dict(leaves(record["fields"]))
    evidence = record["evidence"]
    chosen = st.selectbox(
        "Jump to field",
        [None, *field_values],
        format_func=lambda value: (
            "Choose a field" if value is None else field_label(value)
        ),
        key=f"jump_{record['id']}",
    )
    pages = manifest["selected_pages"]
    matched_pages = [
        loc["page"]
        for e in evidence
        if e["field_path"] == chosen
        for loc in e["locations"]
    ]
    page_key = f"review_page_{record['id']}"
    prior_key = f"review_jump_{record['id']}"
    if st.session_state.get(prior_key) != chosen:
        if matched_pages:
            st.session_state[page_key] = matched_pages[0]
        st.session_state[prior_key] = chosen
    page = st.selectbox("Source page", pages, key=page_key)
    directory = store.document_dir(document["id"])
    upload = Upload(
        (directory / ("preview" + manifest["suffix"])).read_bytes(),
        manifest["suffix"],
        manifest["count"],
    )
    with preview(upload, page - 1) as image:
        image_url = (
            "data:image/png;base64," + base64.b64encode(image_bytes(image)).decode()
        )
        bounds = [0, 0, image.width, image.height]
    regions = {}
    for entry in evidence:
        for loc in entry["locations"]:
            if loc["page"] != page:
                continue
            p = loc["page_bbox"]
            bounds = [p[0], p[1], p[2] - p[0], p[3] - p[1]]
            region = regions.setdefault(
                loc["block_id"], {"bbox": loc["bbox"], "paths": []}
            )
            if entry["field_path"] not in region["paths"]:
                region["paths"].append(entry["field_path"])
    st.caption(
        "Hover over a field or a highlighted area to see its source. Click to keep it selected. "
        "Highlights show approximate text regions, not exact words."
    )
    component_key = f"evidence_{record['id']}_{page}"
    selection = st.session_state.get(component_key, {}).get("selected", chosen)

    def select_field():
        selected = st.session_state.get(component_key, {}).get("selected")
        if selected in field_values:
            destinations = [
                loc["page"]
                for item in evidence
                if item["field_path"] == selected
                for loc in item["locations"]
            ]
            if destinations and page not in destinations:
                st.session_state[page_key] = destinations[0]
            st.session_state[f"jump_{record['id']}"] = selected
        elif selected is None:
            st.session_state[f"jump_{record['id']}"] = None

    viewer(
        data={
            "image": image_url,
            "bounds": bounds,
            "selected": selection,
            "fields": [
                {
                    "path": path,
                    "label": field_label(path),
                    "value": display_value(value),
                    "quotes": [e["quote"] for e in evidence if e["field_path"] == path],
                }
                for path, value in field_values.items()
            ],
            "regions": [
                {**region, "labels": [field_label(path) for path in region["paths"]]}
                for region in regions.values()
            ],
        },
        key=component_key,
        on_selected_change=select_field,
    )
