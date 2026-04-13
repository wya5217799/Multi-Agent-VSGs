function result = vsg_screenshot(system_path, out_path, resolution)
%VSG_SCREENSHOT Capture a Simulink model or subsystem diagram as PNG.
%
%   result = vsg_screenshot(system_path, out_path, resolution)
%
%   system_path  - Model name ('kundur_vsg') or subsystem path
%                  ('kundur_vsg/VSG_ES1'). The model must be loaded.
%   out_path     - Full path for the output PNG file.
%   resolution   - DPI as a double (default 150).
%
%   Returns a struct with fields:
%     ok          - true/false
%     width       - image width in pixels
%     height      - image height in pixels
%     error_msg   - '' on success, error description on failure

    if nargin < 3, resolution = 150; end

    result = struct('ok', false, 'width', 0, 'height', 0, 'error_msg', '');

    try
        % Ensure the system is open (visible) so print can capture it
        open_system(system_path);

        % Use print to capture the diagram
        % -s flag targets the Simulink system window
        print(['-s', system_path], '-dpng', sprintf('-r%d', resolution), out_path);

        % Read back to get dimensions
        info = imfinfo(out_path);
        result.ok = true;
        result.width = info.Width;
        result.height = info.Height;
    catch me
        result.error_msg = char(me.message);
    end
end
