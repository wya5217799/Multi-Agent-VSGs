function result = slx_capture_figure(out_path, figure_id, capture_all, resolution)
%SLX_CAPTURE_FIGURE Capture MATLAB figure window(s) as PNG.
%
%   result = slx_capture_figure(out_path, figure_id, capture_all, resolution)
%
%   out_path     - Output directory for PNG file(s).
%   figure_id    - Scalar figure number to capture, or 0 for gcf (latest).
%   capture_all  - If true, capture every open figure; figure_id is ignored.
%   resolution   - DPI as a double (default 150).
%
%   Returns a struct with fields:
%     ok       - true/false
%     count    - number of figures captured
%     figures  - struct array with {id, path, title, width, height}
%     error_msg - '' on success

    if nargin < 4, resolution = 150; end
    if nargin < 3, capture_all = false; end
    if nargin < 2, figure_id = 0; end

    result = struct('ok', false, 'count', 0, 'figures', [], 'error_msg', '');

    try
        if capture_all
            figs = findobj('Type', 'figure');
            if isempty(figs)
                result.error_msg = 'No open figures found';
                return;
            end
            fig_handles = figs;
        elseif figure_id > 0
            fig_handles = figure_id;
            if ~ishandle(fig_handles) || ~strcmp(get(fig_handles, 'Type'), 'figure')
                result.error_msg = sprintf('Figure %d is not a valid open figure', figure_id);
                return;
            end
        else
            % gcf — current (most recent) figure
            if isempty(findobj('Type', 'figure'))
                result.error_msg = 'No open figures found';
                return;
            end
            fig_handles = gcf;
        end

        fig_results = struct('id', {}, 'path', {}, 'title', {}, 'width', {}, 'height', {});

        for i = 1:numel(fig_handles)
            h = fig_handles(i);
            fig_num = get(h, 'Number');
            fig_title = get(h, 'Name');
            if isempty(fig_title)
                fig_title = sprintf('Figure %d', fig_num);
            end

            fname = fullfile(out_path, sprintf('figure_%d.png', fig_num));
            print(h, '-dpng', sprintf('-r%d', resolution), fname);

            info = imfinfo(fname);
            fig_results(end + 1).id = fig_num; %#ok<AGROW>
            fig_results(end).path = char(fname);
            fig_results(end).title = char(fig_title);
            fig_results(end).width = info.Width;
            fig_results(end).height = info.Height;
        end

        result.ok = true;
        result.count = numel(fig_results);
        result.figures = fig_results;
    catch me
        result.error_msg = char(me.message);
    end
end
