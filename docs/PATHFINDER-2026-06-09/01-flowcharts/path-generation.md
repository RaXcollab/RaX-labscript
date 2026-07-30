# Flowchart — Path-generation factory (iter_path_from_spec) for rastering subsystem

**Purpose:** Convert RasterSpec into lazy iterators yielding (x,y) coordinate tuples via four path-generator algorithms

```mermaid
flowchart TD
    A["iter_path_from_spec<br/>raster_paths.py:276"] -->|validate kind| B{"Parse spec.kind<br/>raster_paths.py:277"}
    B -->|square_x/square-raster-x| C["validate bounds<br/>raster_paths.py:280-281"]
    C -->|bounds exists| D["iter_square_raster_x<br/>raster_paths.py:86-109"]
    D -->|LAZY: yields tuple| E["while row in ys<br/>raster_paths.py:102-109"]
    E -->|alternating xs_fwd/xs_rev| F["yield float x,y<br/>raster_paths.py:109"]
    
    B -->|square_y/square-raster-y| G["validate bounds<br/>raster_paths.py:285-286"]
    G -->|bounds exists| H["iter_square_raster_y<br/>raster_paths.py:112-134"]
    H -->|LAZY: yields tuple| I["while col in xs<br/>raster_paths.py:127-134"]
    I -->|alternating ys_fwd/ys_rev| J["yield float x,y<br/>raster_paths.py:134"]
    
    B -->|spiral/spiral_raster| K["resolve origin<br/>raster_paths.py:290-292"]
    K -->|spec.origin or default| L["iter_spiral_inward<br/>raster_paths.py:141-189"]
    L -->|LAZY: yields tuple| M["while r >= 0<br/>raster_paths.py:173-189"]
    M -->|compute polar coords| N["within_bounds check<br/>raster_paths.py:178,188"]
    N -->|if in bounds| O["yield float x,y<br/>raster_paths.py:179,189"]
    
    B -->|hull/convex_hull| P["validate hull_points<br/>raster_paths.py:303-304"]
    P -->|hull_points exists| Q["iter_convex_hull_fill<br/>raster_paths.py:196-245"]
    Q -->|build Delaunay<br/>raster_paths.py:221-222| R["Delaunay triangulation<br/>scipy.spatial:Delaunay"]
    Q -->|create grid<br/>raster_paths.py:228-229| S["arange_inclusive<br/>raster_paths.py:47-60"]
    S -->|xs,ys arrays| T["order=xy loop<br/>raster_paths.py:234-239"]
    T -->|LAZY: yields tuple| U["find_simplex >= 0 check<br/>raster_paths.py:238,244"]
    U -->|if in hull| V["yield float x,y<br/>raster_paths.py:239,245"]
    
    B -->|unknown kind| W["raise ValueError<br/>raster_paths.py:313"]
    
    D -->|Iterator TargetXY| X["collect_points<br/>raster_paths.py:73-79"]
    H -->|Iterator TargetXY| X
    L -->|Iterator TargetXY| X
    Q -->|Iterator TargetXY| X
    
    X -->|enumerate max_points| Y["append float tuple<br/>raster_paths.py:76"]
    Y -->|break if max_points| Z["return List TargetXY<br/>raster_paths.py:79"]
    
    style D fill:#e1f5ff
    style H fill:#e1f5ff
    style L fill:#e1f5ff
    style Q fill:#e1f5ff
    style X fill:#fff9c4
```

## Side effects
- None for path generators (LAZY — no side effects until iteration)
- collect_points: truncates iterator at max_points
- Delaunay: scipy heap allocation during triangulation (ConvexHull only)

## External deps
- numpy (np.array, np.arange, np.cos, np.sin, np.pi, np.floor)
- scipy.spatial.Delaunay (for hull point-in-triangle test)
- RasterSpec dataclass (defined raster_paths.py:252-273)

## Sources read
- raster_paths.py:276-313 (iter_path_from_spec factory + error handling)
- raster_paths.py:86-109 (iter_square_raster_x — serpentine X primary)
- raster_paths.py:112-134 (iter_square_raster_y — serpentine Y primary)
- raster_paths.py:141-189 (iter_spiral_inward — polar inward spiral)
- raster_paths.py:196-245 (iter_convex_hull_fill — Delaunay grid fill)
- raster_paths.py:73-79 (collect_points — materialize N tuples from iterator)
- raster_paths.py:47-60 (arange_inclusive — grid spacing with stop-inclusive option)
- raster_paths.py:34-45 (bounds_from_points, within_bounds — geometry helpers)
- raster_paths.py:252-273 (RasterSpec dataclass — kind, bounds, params)

## Confidence
High. All four generators read and traced. Factory dispatch verified. RasterSpec fields mapped. Lazy evaluation confirmed (all return Iterator, not List). collect_points materialization step clear.

## Gaps
- include_start parameter (lines 86, 112) not exposed in RasterSpec or iter_path_from_spec — always defaults to True
- Default bounds handling in iter_convex_hull_fill (line 225) computes from hull_points if not provided
- Spiral wrap-around: angle_step_change only applied post-2pi, not per-point — subtle behavior
- Error branches (ValueError) not detailed — assumes valid inputs post-validation
